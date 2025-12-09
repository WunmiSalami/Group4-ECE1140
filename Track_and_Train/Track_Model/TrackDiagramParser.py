"""
Track Diagram Parser - Extracts red line path from professor's diagram
Processes skeleton and segments for manual section labeling
"""

import cv2
import numpy as np
import math
import tkinter as tk
from typing import List, Tuple, Dict
from skimage.morphology import skeletonize
from scipy import ndimage


class TrackDiagramParser:
    """Parse track diagram image and extract red line path."""

    def __init__(self, image_path: str):
        self.image_path = image_path
        self.original_image = None
        self.red_mask = None
        self.green_mask = None
        self.red_pixels = []
        self.green_pixels = []
        self.centerline_pixels_red = []
        self.centerline_pixels_green = []
        self.skeleton_array_red = None
        self.skeleton_array_green = None
        self.clean_skeleton_pixels_red = []
        self.clean_skeleton_pixels_green = []
        self.segments_red = []
        self.segments_green = []

    def load_image(self):
        """Load the track diagram image."""
        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            raise FileNotFoundError(f"Could not load image: {self.image_path}")

    def find_red_pixels(self):
        """Find all red pixels in the image."""
        hsv = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2HSV)

        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 100, 100])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        self.red_mask = cv2.bitwise_or(mask1, mask2)

        red_coords = np.where(self.red_mask > 0)
        self.red_pixels = [(x, y) for y, x in zip(red_coords[0], red_coords[1])]

    def find_green_pixels(self):
        """Find all green pixels in the image."""

        hsv = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2HSV)

        lower_green1 = np.array([35, 40, 40])
        upper_green1 = np.array([85, 255, 255])
        lower_green2 = np.array([85, 40, 40])
        upper_green2 = np.array([95, 255, 255])

        mask1 = cv2.inRange(hsv, lower_green1, upper_green1)
        mask2 = cv2.inRange(hsv, lower_green2, upper_green2)
        self.green_mask = cv2.bitwise_or(mask1, mask2)

        green_coords = np.where(self.green_mask > 0)
        self.green_pixels = [(x, y) for y, x in zip(green_coords[0], green_coords[1])]

    def extract_centerline_red(self):
        """Extract red centerline using skeletonization and filter by thickness."""

        distance_red = ndimage.distance_transform_edt(self.red_mask)
        skeleton_red = skeletonize(self.red_mask > 0)
        self.skeleton_array_red = skeleton_red.astype(np.uint8)

        thickness_threshold = 3
        skeleton_coords_red = np.where(skeleton_red)
        filtered_centerline_red = []

        for y, x in zip(skeleton_coords_red[0], skeleton_coords_red[1]):
            thickness = distance_red[y, x]
            if thickness >= thickness_threshold:
                filtered_centerline_red.append((x, y))

        self.centerline_pixels_red = filtered_centerline_red

    def extract_centerline_green(self):
        """Extract green centerline using skeletonization and filter by thickness."""

        distance_green = ndimage.distance_transform_edt(self.green_mask)
        skeleton_green = skeletonize(self.green_mask > 0)
        self.skeleton_array_green = skeleton_green.astype(np.uint8)

        thickness_threshold = 3
        skeleton_coords_green = np.where(skeleton_green)
        filtered_centerline_green = []

        for y, x in zip(skeleton_coords_green[0], skeleton_coords_green[1]):
            thickness = distance_green[y, x]
            if thickness >= thickness_threshold:
                filtered_centerline_green.append((x, y))

        self.centerline_pixels_green = filtered_centerline_green

    def remove_red_arrowheads(self):
        """Remove arrowhead pixels to create clean breaks at junctions."""

        height, width = self.skeleton_array_red.shape
        skeleton_map = np.zeros((height, width), dtype=bool)

        for x, y in self.centerline_pixels_red:
            skeleton_map[y, x] = True

        junction_points = []

        for x, y in self.centerline_pixels_red:
            neighbors = 0
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and skeleton_map[ny, nx]:
                        neighbors += 1

            if neighbors >= 3:
                junction_points.append((x, y))

        removed_set = set()
        for jx, jy in junction_points:
            removed_set.add((jx, jy))
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    removed_set.add((jx + dx, jy + dy))

        temp_clean = [
            (x, y) for x, y in self.centerline_pixels_red if (x, y) not in removed_set
        ]
        self.clean_skeleton_pixels_red = self._filter_small_components(
            temp_clean, min_size=16
        )

    def remove_green_arrowheads(self):
        """Remove arrowhead pixels to create clean breaks at junctions."""

        height, width = self.skeleton_array_green.shape
        skeleton_map = np.zeros((height, width), dtype=bool)

        for x, y in self.centerline_pixels_green:
            skeleton_map[y, x] = True

        junction_points = []

        for x, y in self.centerline_pixels_green:
            neighbors = 0
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and skeleton_map[ny, nx]:
                        neighbors += 1

            if neighbors >= 3:
                junction_points.append((x, y))

        removed_set = set()
        for jx, jy in junction_points:
            removed_set.add((jx, jy))
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    removed_set.add((jx + dx, jy + dy))

        temp_clean = [
            (x, y) for x, y in self.centerline_pixels_green if (x, y) not in removed_set
        ]

        self.clean_skeleton_pixels_green = self._filter_small_components(
            temp_clean, min_size=20
        )

    def _filter_small_components(
        self, pixels: List[Tuple[int, int]], min_size: int = 16
    ) -> List[Tuple[int, int]]:
        """Remove small disconnected components."""
        if not pixels:
            return []

        pixel_set = set(pixels)
        visited = set()
        components = []

        def bfs(start):
            component = []
            queue = [start]
            visited.add(start)

            while queue:
                x, y = queue.pop(0)
                component.append((x, y))

                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        neighbor = (x + dx, y + dy)
                        if neighbor in pixel_set and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

            return component

        for pixel in pixels:
            if pixel not in visited:
                component = bfs(pixel)
                components.append(component)

        filtered = []
        for component in components:
            if len(component) >= min_size:
                filtered.extend(component)

        return filtered

    def find_connected_segments_red(self):
        """Group continuous pixels into segments and create bounding boxes."""

        if not self.clean_skeleton_pixels_red:
            return

        pixel_set = set(self.clean_skeleton_pixels_red)
        visited = set()
        self.segments_red = []

        def bfs(start):
            component = []
            queue = [start]
            visited.add(start)

            while queue:
                x, y = queue.pop(0)
                component.append((x, y))

                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        neighbor = (x + dx, y + dy)
                        if neighbor in pixel_set and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

            return component

        for pixel in self.clean_skeleton_pixels_red:
            if pixel not in visited:
                segment_pixels = bfs(pixel)

                xs = [p[0] for p in segment_pixels]
                ys = [p[1] for p in segment_pixels]

                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                x_range = max_x - min_x
                trim_x = int(x_range * 0.12)
                min_x += trim_x
                max_x -= trim_x

                vertical_padding = 25
                min_y -= vertical_padding
                max_y += vertical_padding

                min_x = max(0, min_x)
                min_y = max(0, min_y)
                max_x = min(self.original_image.shape[1] - 1, max_x)
                max_y = min(self.original_image.shape[0] - 1, max_y)

                self.segments_red.append(
                    {
                        "pixels": segment_pixels,
                        "bbox": (min_x, min_y, max_x, max_y),
                        "section_label": None,
                    }
                )

    def find_connected_segments_green(self):
        """Group continuous green pixels into segments and create bounding boxes."""

        if not self.clean_skeleton_pixels_green:
            return

        pixel_set = set(self.clean_skeleton_pixels_green)
        visited = set()
        self.segments_green = []

        def bfs(start):
            component = []
            queue = [start]
            visited.add(start)

            while queue:
                x, y = queue.pop(0)
                component.append((x, y))

                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        neighbor = (x + dx, y + dy)
                        if neighbor in pixel_set and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
            return component

        for pixel in self.clean_skeleton_pixels_green:
            if pixel not in visited:
                segment_pixels = bfs(pixel)

                xs = [p[0] for p in segment_pixels]
                ys = [p[1] for p in segment_pixels]

                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                x_range = max_x - min_x
                trim_x = int(x_range * 0.12)
                min_x += trim_x
                max_x -= trim_x

                vertical_padding = 25
                min_y -= vertical_padding
                max_y += vertical_padding

                min_x = max(0, min_x)
                min_y = max(0, min_y)
                max_x = min(self.original_image.shape[1] - 1, max_x)
                max_y = min(self.original_image.shape[0] - 1, max_y)

                self.segments_green.append(
                    {
                        "pixels": segment_pixels,
                        "bbox": (min_x, min_y, max_x, max_y),
                        "section_label": None,
                    }
                )

    def manually_label_segments_red(self):
        """Manually hardcode section labels for each segment.

        EDIT THE DICTIONARY BELOW to assign section names to segment numbers.
        """

        # ============================================
        # MANUALLY EDIT THIS DICTIONARY
        # ============================================
        manual_labels = {
            0: "C",
            1: "B",
            3: "A",
            4: "D",
            5: "YARD",
            7: "F",
            8: "E",
            9: "G",
            11: "H",
            12: "T",
            13: "S",
            14: "R",
            15: "H",
            16: "H",
            17: "Q",
            18: "L",
            19: "P",
            20: "M",
            21: "O",
            22: "K",
            23: "I",
            24: "N",
            25: "J",
            26: "J",
            # 6, 12 are nothing - don't include them
        }

        for seg_idx, label in manual_labels.items():
            if seg_idx < len(self.segments_red):
                self.segments_red[seg_idx]["section_label"] = label

        # Join segments with same label into contiguous paths
        self._merge_segments_by_label_red()

    def manually_label_segments_green(self):
        """Manually hardcode section labels for each green segment."""

        # ============================================
        # MANUALLY EDIT THIS DICTIONARY for green
        # ============================================
        manual_labels_green = {
            2: "C",
            7: "B",
            5: "A",
            1: "D",
            0: "D",
            4: "D",
            6: "E",
            8: "F",
            9: "Z",
            10: "G",
            11: "Y",
            12: "H",
            13: "YARD",
            14: "YARD",
            20: "X",
            21: "W",
            22: "W",
            23: "V",
            19: "J",
            16: "I",
            17: "I",
            18: "I",
            25: "K",
            26: "U",
            27: "T",
            28: "L",
            31: "S",
            36: "M",
            32: "R",
            35: "N",
            34: "N",
            30: "Q",
            33: "O",
            29: "P",
        }

        for seg_idx, label in manual_labels_green.items():
            if seg_idx < len(self.segments_green):
                self.segments_green[seg_idx]["section_label"] = label

        # Merge green segments with the same label
        self._merge_segments_by_label_green()

    def _merge_segments_by_label_green(self):
        """Merge green segments with the same label into contiguous paths."""

        label_groups = {}
        for segment in self.segments_green:
            label = segment.get("section_label")
            if label:
                if label not in label_groups:
                    label_groups[label] = []
                label_groups[label].append(segment)

        merged_segments = []
        processed_labels = set()

        for segment in self.segments_green:
            label = segment.get("section_label")
            if not label:
                merged_segments.append(segment)
                continue
            if label in processed_labels:
                continue

            same_label_segments = label_groups[label]
            if len(same_label_segments) == 1:
                merged_segments.append(segment)
            else:

                all_pixels = list(same_label_segments[0]["pixels"])
                remaining_segs = same_label_segments[1:]

                while remaining_segs:
                    min_dist = float("inf")
                    closest_idx = 0
                    closest_p1 = None
                    closest_p2 = None

                    for idx, seg in enumerate(remaining_segs):
                        for p1 in all_pixels:
                            for p2 in seg["pixels"]:
                                dist = (
                                    (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2
                                ) ** 0.5
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_idx = idx
                                    closest_p1 = p1
                                    closest_p2 = p2

                    if closest_p1 and closest_p2:
                        x1, y1 = closest_p1
                        x2, y2 = closest_p2

                        dx = abs(x2 - x1)
                        dy = abs(y2 - y1)
                        sx = 1 if x1 < x2 else -1
                        sy = 1 if y1 < y2 else -1
                        err = dx - dy

                        x, y = x1, y1
                        line_pixels = []

                        while True:
                            line_pixels.append((x, y))
                            if x == x2 and y == y2:
                                break
                            e2 = 2 * err
                            if e2 > -dy:
                                err -= dy
                                x += sx
                            if e2 < dx:
                                err += dx
                                y += sy

                        all_pixels.extend(line_pixels)
                        all_pixels.extend(remaining_segs[closest_idx]["pixels"])
                    remaining_segs.pop(closest_idx)

                all_pixels = list(dict.fromkeys(all_pixels))

                xs = [p[0] for p in all_pixels]
                ys = [p[1] for p in all_pixels]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                merged_segment = {
                    "pixels": all_pixels,
                    "bbox": (min_x, min_y, max_x, max_y),
                    "section_label": label,
                }
                merged_segments.append(merged_segment)

            processed_labels.add(label)

        self.segments_green = merged_segments

    def _merge_segments_by_label_red(self):
        """Merge segments with the same label into single contiguous paths."""
        # Group segments by label
        label_groups = {}
        for segment in self.segments_red:
            label = segment.get("section_label")
            if label:  # Only merge labeled segments
                if label not in label_groups:
                    label_groups[label] = []
                label_groups[label].append(segment)

        # For each label with multiple segments, merge them
        merged_segments = []
        processed_labels = set()

        for segment in self.segments_red:
            label = segment.get("section_label")

            # If no label, keep as is
            if not label:
                merged_segments.append(segment)
                continue

            # If already processed this label, skip
            if label in processed_labels:
                continue

            # Get all segments with this label
            same_label_segments = label_groups[label]

            if len(same_label_segments) == 1:
                # Single segment, keep as is
                merged_segments.append(segment)
            else:

                # Start with first segment
                all_pixels = list(same_label_segments[0]["pixels"])
                remaining_segs = same_label_segments[1:]

                # Connect each remaining segment to the growing chain
                while remaining_segs:
                    # Find closest segment to current chain
                    min_dist = float("inf")
                    closest_idx = 0
                    closest_p1 = None
                    closest_p2 = None

                    for idx, seg in enumerate(remaining_segs):
                        for p1 in all_pixels:
                            for p2 in seg["pixels"]:
                                dist = (
                                    (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2
                                ) ** 0.5
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_idx = idx
                                    closest_p1 = p1
                                    closest_p2 = p2

                    # Draw line between closest points using Bresenham's algorithm
                    if closest_p1 and closest_p2:
                        x1, y1 = closest_p1
                        x2, y2 = closest_p2

                        dx = abs(x2 - x1)
                        dy = abs(y2 - y1)
                        sx = 1 if x1 < x2 else -1
                        sy = 1 if y1 < y2 else -1
                        err = dx - dy

                        x, y = x1, y1
                        line_pixels = []

                        while True:
                            line_pixels.append((x, y))
                            if x == x2 and y == y2:
                                break
                            e2 = 2 * err
                            if e2 > -dy:
                                err -= dy
                                x += sx
                            if e2 < dx:
                                err += dx
                                y += sy

                        # Add connecting line and next segment
                        all_pixels.extend(line_pixels)
                        all_pixels.extend(remaining_segs[closest_idx]["pixels"])

                    remaining_segs.pop(closest_idx)

                # Remove duplicates
                all_pixels = list(dict.fromkeys(all_pixels))

                # Calculate new bounding box
                xs = [p[0] for p in all_pixels]
                ys = [p[1] for p in all_pixels]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                # Create merged segment
                merged_segment = {
                    "pixels": all_pixels,
                    "bbox": (min_x, min_y, max_x, max_y),
                    "section_label": label,
                }
                merged_segments.append(merged_segment)
            processed_labels.add(label)

        # Replace segments with merged version
        self.segments_red = merged_segments

    def get_section_path_red(self, section_name: str) -> List[Tuple[int, int]]:
        """Get skeleton pixels for a specific RED line section."""
        for segment in self.segments_red:
            if segment["section_label"] == section_name:
                return segment["pixels"]
        return []

    def get_section_path_green(self, section_name: str) -> List[Tuple[int, int]]:
        """Get skeleton pixels for a specific GREEN line section."""
        for segment in self.segments_green:
            if segment["section_label"] == section_name:
                return segment["pixels"]
        return []

    def order_all_segments_red(self):
        """Final pass to order pixels in each segment before output to visualizer."""

        for segment in self.segments_red:
            if not segment["pixels"]:
                continue

            pixels = segment["pixels"]

            # Find the two furthest pixels (endpoints)
            max_dist = 0
            endpoint1 = pixels[0]
            endpoint2 = pixels[0]

            for i, p1 in enumerate(pixels):
                for p2 in pixels[i + 1 :]:
                    dist = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
                    if dist > max_dist:
                        max_dist = dist
                        endpoint1 = p1
                        endpoint2 = p2

            # Start from endpoint1 and follow path to endpoint2
            pixel_set = set(pixels)
            visited = set()
            ordered_pixels = []

            current = endpoint1
            visited.add(current)
            ordered_pixels.append(current)

            # Follow path by always moving to nearest unvisited neighbor
            while len(visited) < len(pixels):
                min_dist = float("inf")
                next_pixel = None

                # Check all 8 neighbors
                cx, cy = current
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        neighbor = (cx + dx, cy + dy)

                        if neighbor in pixel_set and neighbor not in visited:
                            dist = (
                                (current[0] - neighbor[0]) ** 2
                                + (current[1] - neighbor[1]) ** 2
                            ) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                next_pixel = neighbor

                if next_pixel is None:
                    # No adjacent neighbor found, find closest unvisited pixel
                    for p in pixels:
                        if p not in visited:
                            dist = (
                                (current[0] - p[0]) ** 2 + (current[1] - p[1]) ** 2
                            ) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                next_pixel = p

                if next_pixel is None:
                    break

                current = next_pixel
                visited.add(current)
                ordered_pixels.append(current)

            segment["pixels"] = ordered_pixels

    def order_all_segments_green(self):
        """Order pixels in each green segment for output to visualizer."""

        for segment in self.segments_green:
            if not segment["pixels"]:
                continue

            pixels = segment["pixels"]

            # Choose endpoints based on section
            if segment.get("section_label") == "P":
                # Use custom ordering for section P
                ordered_pixels = self.order_section_p_pixels(pixels)
            else:
                # Find the two furthest pixels (endpoints)
                max_dist = 0
                endpoint1 = pixels[0]
                endpoint2 = pixels[0]

                for i, p1 in enumerate(pixels):
                    for p2 in pixels[i + 1 :]:
                        dist = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
                        if dist > max_dist:
                            max_dist = dist
                            endpoint1 = p1
                            endpoint2 = p2

                # ORDER THE PIXELS (for non-P sections)
                pixel_set = set(pixels)
                visited = set()
                ordered_pixels = []

                current = endpoint1
                visited.add(current)
                ordered_pixels.append(current)

                while len(visited) < len(pixels):
                    min_dist = float("inf")
                    next_pixel = None
                    cx, cy = current

                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if dx == 0 and dy == 0:
                                continue
                            neighbor = (cx + dx, cy + dy)
                            if neighbor in pixel_set and neighbor not in visited:
                                dist = (
                                    (current[0] - neighbor[0]) ** 2
                                    + (current[1] - neighbor[1]) ** 2
                                ) ** 0.5
                                if dist < min_dist:
                                    min_dist = dist
                                    next_pixel = neighbor

                    if next_pixel is None:
                        for p in pixels:
                            if p not in visited:
                                dist = (
                                    (current[0] - p[0]) ** 2 + (current[1] - p[1]) ** 2
                                ) ** 0.5
                                if dist < min_dist:
                                    min_dist = dist
                                    next_pixel = p

                    if next_pixel is None:
                        break

                    current = next_pixel
                    visited.add(current)
                    ordered_pixels.append(current)

            segment["pixels"] = ordered_pixels

    def order_section_p_pixels(self, pixels):
        """
        Orders pixels for segment P using strict three-segment logic:
        1. Segment 1: strictly decreasing X from min Y (1242)
        2. Segment 2: strictly decreasing Y from min X (toward max Y 1044)
        3. Segment 3: strictly increasing X (or remaining pixels) to complete the segment

        pixels: list of (x, y) tuples or np.int64 pairs
        returns: ordered list of pixels
        """
        # Convert to list of tuples if using numpy
        pixels = [tuple(p) for p in pixels]

        # Track used pixels
        used = set()
        ordered = []

        # Segment 1: Start at min Y
        max_y = max(p[1] for p in pixels)  # Find maximum Y value
        candidates = [p for p in pixels if p[1] == max_y]  # Pixels with max Y
        start_pixel = max(candidates, key=lambda p: p[0])  # Choose the one with max X

        ordered.append(start_pixel)
        used.add(start_pixel)
        current_pixel = start_pixel

        # Segment 1: strictly decreasing Y
        while True:
            candidates = [
                p for p in pixels if p not in used and p[1] <= current_pixel[1]
            ]
            if not candidates:
                break
            # pick pixel with minimal combined X and Y difference
            next_pixel = min(
                candidates,
                key=lambda p: abs(p[0] - current_pixel[0])
                + abs(p[1] - current_pixel[1]),
            )
            ordered.append(next_pixel)
            used.add(next_pixel)
            current_pixel = next_pixel

        # Segment 2: strictly decreasing Y toward max Y (1044)
        current_pixel = ordered[-1]
        while True:
            candidates = [
                p for p in pixels if p not in used and p[1] > current_pixel[1]
            ]
            if not candidates:
                break
            next_pixel = min(candidates, key=lambda p: abs(p[0] - current_pixel[0]))
            ordered.append(next_pixel)
            used.add(next_pixel)
            current_pixel = next_pixel

        return ordered

    def parse(self):
        """Parse the image and extract segments for both red and green lines."""
        self.load_image()

        # RED LINE PROCESSING
        self.find_red_pixels()
        self.extract_centerline_red()
        self.remove_red_arrowheads()
        self.find_connected_segments_red()
        self.manually_label_segments_red()
        self.order_all_segments_red()

        # GREEN LINE PROCESSING
        self.find_green_pixels()
        self.extract_centerline_green()
        self.remove_green_arrowheads()
        self.find_connected_segments_green()
        self.manually_label_segments_green()
        self.order_all_segments_green()
        return self

    def visualize(self):
        """Show two views side by side: segments with bounding boxes, and final labeled sections."""
        root = tk.Tk()
        root.title("Track Diagram Parser - Segments & Labels")
        root.geometry("2400x900")

        container = tk.Frame(root)
        container.pack(fill=tk.BOTH, expand=True)

        # LEFT: Red segments with bounding boxes
        left_frame = tk.Frame(container)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_label = tk.Label(
            left_frame, text="Red Segments", font=("Arial", 10, "bold")
        )
        left_label.pack()

        left_canvas = tk.Canvas(left_frame, bg="white")
        left_canvas.pack(fill=tk.BOTH, expand=True)

        scale = 0.5

        for segment in self.segments_red:
            # Skip empty segments
            if not segment["pixels"]:
                continue

            # Draw pixels
            for x, y in segment["pixels"]:
                left_canvas.create_rectangle(
                    int(x * scale),
                    int(y * scale),
                    int(x * scale) + 1,
                    int(y * scale) + 1,
                    fill="red",
                    outline="",
                )

            # Draw label at approximate center
            if segment.get("section_label"):
                xs = [p[0] for p in segment["pixels"]]
                ys = [p[1] for p in segment["pixels"]]
                center_x = sum(xs) // len(xs)
                center_y = sum(ys) // len(ys)
                left_canvas.create_text(
                    int(center_x * scale),
                    int(center_y * scale),
                    text=segment["section_label"],
                    font=("Arial", 12, "bold"),
                    fill="blue",
                )

        scale = 0.5

        # RIGHT: Labeled sections
        right_frame = tk.Frame(container)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        right_label = tk.Label(right_frame, text="Labels", font=("Arial", 10, "bold"))
        right_label.pack()

        right_canvas = tk.Canvas(right_frame, bg="white")
        right_canvas.pack(fill=tk.BOTH, expand=True)

        for segment in self.segments_green:
            for x, y in segment["pixels"]:
                right_canvas.create_rectangle(
                    int(x * scale),
                    int(y * scale),
                    int(x * scale) + 1,
                    int(y * scale) + 1,
                    fill="green",
                    outline="",
                )

            if segment["pixels"] and segment["section_label"]:
                xs = [p[0] for p in segment["pixels"]]
                ys = [p[1] for p in segment["pixels"]]
                center_x = sum(xs) // len(xs)
                center_y = min(ys) - 30
                right_canvas.create_text(
                    int(center_x * scale),
                    int(center_y * scale),
                    text=segment["section_label"],
                    font=("Arial", 12, "bold"),
                    fill="blue",
                )

        root.mainloop()


def main():
    """Test the parser."""
    parser = TrackDiagramParser("track.png")
    parser.parse()
    parser.visualize()


if __name__ == "__main__":
    main()
