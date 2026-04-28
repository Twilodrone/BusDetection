import logging
import os
import time
from pathlib import Path
from typing import Any

import cv2
from dotenv import load_dotenv

try:
    import torch
    import torch.nn as nn
    from torchvision import transforms
except Exception:  # noqa: BLE001
    torch = None
    nn = None
    transforms = None

from Common.storage import BusEvent, DetectionStorage, utc_now_iso_ms


class BusPredictor:
    """Инференс бинарного классификатора автобуса."""

    def __init__(self, model_path: str, threshold: float = 0.5) -> None:
        if torch is None or nn is None or transforms is None:
            raise RuntimeError("Для инференса требуются torch/torchvision")

        self.threshold = threshold
        checkpoint = torch.load(model_path, map_location="cpu")
        if not isinstance(checkpoint, nn.Module):
            raise RuntimeError("MODEL_PATH должен загружаться как nn.Module через torch.load")

        self.model: nn.Module = checkpoint.eval()
        self.transform = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def predict(self, frame_bgr: Any) -> tuple[bool, float]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).unsqueeze(0)
        with torch.no_grad():
            output = self.model(tensor)

        if output.ndim == 2 and output.shape[1] >= 2:
            confidence = float(torch.softmax(output, dim=1)[0, 1].item())
        else:
            confidence = float(torch.sigmoid(output.flatten()[0]).item())
        return confidence >= self.threshold, confidence


def read_rtsp_frame(rtsp_url: str) -> Any:
    cap = cv2.VideoCapture(rtsp_url)
    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Не удалось прочитать кадр RTSP")
        return frame
    finally:
        cap.release()


def save_frame(frame: Any, output_dir: Path, ts_utc: str) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"bus_{ts_utc.replace(':', '-').replace('.', '-')}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    rtsp_url = os.getenv("RTSP_URL")
    model_path = os.getenv("MODEL_PATH", "Model/best_effnet_b0.pth")
    db_path = os.getenv("DB_PATH", "data/detections.sqlite3")
    images_dir = Path(os.getenv("IMAGES_DIR", "data/images"))
    poll_interval_sec = float(os.getenv("POLL_INTERVAL_SEC", "2"))
    threshold = float(os.getenv("BUS_CONFIDENCE_THRESHOLD", "0.5"))

    if not rtsp_url:
        raise RuntimeError("Не задан RTSP_URL")

    predictor = BusPredictor(model_path=model_path, threshold=threshold)
    storage = DetectionStorage(db_path)

    logging.info("Detector started")
    while True:
        started = time.time()
        ts_utc = utc_now_iso_ms()
        frame = read_rtsp_frame(rtsp_url)
        detected, confidence = predictor.predict(frame)
        image_path = save_frame(frame, images_dir, ts_utc)

        storage.insert_bus_event(
            BusEvent(
                ts_utc=ts_utc,
                bus_detected=detected,
                confidence=confidence,
                image_path=image_path,
                meta={"threshold": threshold},
            )
        )

        logging.info("bus=%s confidence=%.3f image=%s", detected, confidence, image_path)
        time.sleep(max(0.0, poll_interval_sec - (time.time() - started)))


if __name__ == "__main__":
    main()
