import cv2
from ultralytics import YOLO

model = YOLO("vision/model/yolo26n.pt")
camera = cv2.VideoCapture(0)

while True:
    ok, frame = camera.read()

    if not ok:
        print("Webcam inaccessible")
        break

    results = model(frame, conf=0.60, verbose=False)

    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0])
            label = model.names[class_id]

            if label == "person":
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    "Intrus detectee",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )

    cv2.imshow("SENTINEL-X Vision", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()