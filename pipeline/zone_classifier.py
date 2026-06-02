# pipeline/zone_classifier.py
import cv2
import numpy as np

class Zone:
    def __init__(self, name: str, polygon: list[list[float]]):
        """
        polygon: List of [x, y] coordinates defining the polygon vertices.
        """
        self.name = name
        # Convert to numpy array of shape (N, 1, 2) and type int32 for opencv
        self.polygon = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))

    def contains_point(self, point: tuple[float, float]) -> bool:
        # cv2.pointPolygonTest returns >= 0 if inside or on edge
        dist = cv2.pointPolygonTest(self.polygon, (float(point[0]), float(point[1])), False)
        return dist >= 0

class ZoneClassifier:
    def __init__(self, zones: list[Zone] | None = None):
        # Default zones if none provided (e.g., checkout, aisles, shelves)
        if zones is None:
            self.zones = [
                Zone("checkout", [[0, 300], [400, 300], [400, 600], [0, 600]]),
                Zone("aisle_1", [[400, 0], [800, 0], [800, 400], [400, 400]]),
                Zone("shelf_1", [[400, 400], [800, 400], [800, 600], [400, 600]])
            ]
        else:
            self.zones = zones

    def classify(self, bbox: list[float], class_name: str = "person") -> str:
        """
        Classifies which zone a bounding box belongs to.
        bbox: [x1, y1, x2, y2]
        """
        # For person, use bottom center (standing point on floor)
        # For objects, use center
        x1, y1, x2, y2 = bbox
        if class_name == "person":
            point = ((x1 + x2) / 2.0, y2)
        else:
            point = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

        for zone in self.zones:
            if zone.contains_point(point):
                return zone.name
        return "unknown"
