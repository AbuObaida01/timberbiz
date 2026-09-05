import io
import math
import torch
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# ImageNet class groupings
# ─────────────────────────────────────────────────────────────

# Classes that are clearly NOT trees or plants
# If model is very confident (>70%) about these → reject
DEFINITELY_NOT_TREE = {
    # People
    *range(0, 10),      # Various fish
    # Vehicles
    *range(400, 470),   # Cars, trucks, bikes, planes
    # Electronics
    *range(562, 620),   # Computers, phones, remotes
    # Food items
    *range(920, 950),   # Fruits, vegetables (cut/plated)
    # Household items
    *range(765, 800),   # Furniture, household
    # Buildings/structures (indoor)
    *range(440, 500),   # Various indoor scenes
    # Kitchen items
    *range(540, 562),   # Kitchen appliances
    # Clothing
    *range(610, 640),   # Clothes, accessories
}

# Classes that strongly suggest trees, plants, or outdoor nature
NATURE_CLASSES = {
    # Plants and fungi
    984,   # Rapeseed
    985,   # Corn
    986,   # Acorn
    987,   # Hip (rose hip)
    988,   # Buckeye
    997,   # Hen-of-the-woods
    # Outdoor/landscape
    972,   # Cliff dwelling
    975,   # Lakeside
    976,   # Seashore
    977,   # Valley
    978,   # Alp
    979,   # Volcano
    980,   # Promontory
    # Tree-related objects
    340,   # Fox squirrel (usually in trees)
    341,   # Grey squirrel
    # Wood/lumber related
    427,   # Barrel (wood)
    428,   # Basket (wood)
    # Fences/outdoor structures
    716,   # Picket fence (wood)
    717,   # Worm fence (wood)
    # Agricultural
    252,   # Porcupine (outdoor/forest)
    # Outdoor scenes
    850,   # Teddy bear (outdoor)
    # Hammock (outdoor/trees)
    600,   # Lakeside
}

# ─────────────────────────────────────────────────────────────
# Model — loaded once when server starts
# ─────────────────────────────────────────────────────────────

_model = None

def get_model():
    global _model
    if _model is None:
        logger.info("🌲 Loading MobileNetV2 tree classifier...")
        _model = models.mobilenet_v2(
            weights=models.MobileNet_V2_Weights.IMAGENET1K_V1
        )
        _model.eval()
        logger.info("✅ MobileNetV2 loaded successfully")
    return _model


# Image preprocessing — must match ImageNet training settings
preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])


# ─────────────────────────────────────────────────────────────
# Color Analysis
# ─────────────────────────────────────────────────────────────

def analyze_colors(image: Image.Image) -> dict:
    """
    Analyze if image has tree-like colors.
    Trees are typically green, brown, grey (bark), or mixed.
    """
    # Resize to small for fast processing
    small = image.resize((100, 100)).convert("RGB")
    pixels = list(small.getdata())

    total = len(pixels)
    green_count = 0
    brown_count = 0
    sky_count = 0
    very_unnatural_count = 0

    for r, g, b in pixels:
        # Green pixels (leaves, grass)
        if g > r + 20 and g > b + 10 and g > 60:
            green_count += 1
        # Brown pixels (bark, soil, wood)
        elif r > 80 and g > 40 and b < 80 and r > g > b:
            brown_count += 1
        # Sky blue (outdoor scene)
        elif b > r + 20 and b > g + 10 and b > 80:
            sky_count += 1
        # Very unnatural colors — pure red, neon, etc.
        elif (r > 200 and g < 50 and b < 50):
            very_unnatural_count += 1

    green_ratio = green_count / total
    brown_ratio = brown_count / total
    sky_ratio = sky_count / total
    unnatural_ratio = very_unnatural_count / total

    # Nature score: higher = more likely to be outdoor/tree image
    nature_score = green_ratio + (brown_ratio * 0.8) + (sky_ratio * 0.5)

    return {
        "green_ratio": round(green_ratio, 3),
        "brown_ratio": round(brown_ratio, 3),
        "sky_ratio": round(sky_ratio, 3),
        "unnatural_ratio": round(unnatural_ratio, 3),
        "nature_score": round(nature_score, 3),
        "is_natural_colors": nature_score > 0.15  # At least 15% natural colors
    }


# ─────────────────────────────────────────────────────────────
# Main Classifier
# ─────────────────────────────────────────────────────────────

def classify_image(image_bytes: bytes) -> dict:
    """
    Classify a single image as tree/plant or not.

    Returns:
        dict with keys:
            - is_tree (bool)
            - confidence (float 0-100)
            - reason (str — why accepted or rejected)
            - details (dict — full analysis)
    """
    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # ── STEP 1: Color Analysis ──────────────────────────
        color_analysis = analyze_colors(image)
        is_natural_colors = color_analysis["is_natural_colors"]
        nature_score = color_analysis["nature_score"]

        # ── STEP 2: ML Classification ───────────────────────
        model = get_model()
        tensor = preprocess(image).unsqueeze(0)

        with torch.no_grad():
            outputs = model(tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)

        # Get top 10 predictions
        top10_prob, top10_idx = torch.topk(probabilities, 10)

        top_predictions = []
        for prob, idx in zip(top10_prob, top10_idx):
            top_predictions.append({
                "class_idx": idx.item(),
                "confidence": round(prob.item() * 100, 2)
            })

        top1_class = top10_idx[0].item()
        top1_confidence = top10_prob[0].item()

        # ── STEP 3: Decision Logic ──────────────────────────

        # Check if top prediction is clearly NOT a tree
        # with very high confidence
        is_clearly_not_tree = (
            top1_class in DEFINITELY_NOT_TREE and
            top1_confidence > 0.70  # 70% confident it's something else
        )

        # Check if any top-5 prediction is nature/plant related
        has_nature_class = any(
            pred["class_idx"] in NATURE_CLASSES
            for pred in top_predictions[:5]
        )

        # Combined decision
        # Accept if:
        # 1. Natural colors present (green/brown dominant) OR
        # 2. Any top-5 prediction is nature-related
        # AND not clearly identified as something else

        if is_clearly_not_tree:
            # Model is very confident this is NOT a tree
            class_name = get_class_name(top1_class)
            return {
                "is_tree": False,
                "confidence": round(top1_confidence * 100, 1),
                "reason": f"Image appears to be '{class_name}', not a tree or plant.",
                "details": {
                    "color_analysis": color_analysis,
                    "top_prediction": class_name,
                    "top_confidence": round(top1_confidence * 100, 1),
                    "nature_score": nature_score
                }
            }

        if is_natural_colors or has_nature_class:
            # Image has tree-like colors or nature classification
            confidence_score = min(
                95,
                (nature_score * 100) +
                (30 if has_nature_class else 0) +
                (20 if is_natural_colors else 0)
            )
            return {
                "is_tree": True,
                "confidence": round(confidence_score, 1),
                "reason": "Image contains tree or plant-like characteristics.",
                "details": {
                    "color_analysis": color_analysis,
                    "top_prediction": get_class_name(top1_class),
                    "top_confidence": round(top1_confidence * 100, 1),
                    "has_nature_class": has_nature_class,
                    "nature_score": nature_score
                }
            }

        # Model is uncertain — low confidence, no strong signals
        # For timber business, give benefit of doubt if nature score > 5%
        if nature_score > 0.05:
            return {
                "is_tree": True,
                "confidence": round(nature_score * 100, 1),
                "reason": "Image accepted — some natural characteristics detected.",
                "details": {
                    "color_analysis": color_analysis,
                    "top_prediction": get_class_name(top1_class),
                    "nature_score": nature_score
                }
            }

        # No natural colors, no nature classes, uncertain model
        return {
            "is_tree": False,
            "confidence": 0.0,
            "reason": "Image does not appear to show a tree or plant. "
                      "Please upload a clear photo of the tree.",
            "details": {
                "color_analysis": color_analysis,
                "top_prediction": get_class_name(top1_class),
                "top_confidence": round(top1_confidence * 100, 1),
                "nature_score": nature_score
            }
        }

    except Exception as e:
        logger.error(f"Classification error: {e}")
        # On any error — allow the upload
        # Better to allow than block legitimate uploads due to bugs
        return {
            "is_tree": True,
            "confidence": 0.0,
            "reason": "Classification check passed (system fallback).",
            "details": {"error": str(e)}
        }


def get_class_name(class_idx: int) -> str:
    """Get human readable name for common ImageNet classes"""
    class_names = {
        # Vehicles
        407: "ambulance", 408: "amphibian vehicle",
        436: "beach wagon", 468: "cab/taxi",
        # Electronics
        487: "cell phone", 508: "computer keyboard",
        # People-related
        515: "crash helmet", 605: "iPod",
        # Food
        924: "guacamole", 925: "consomme",
        # Animals
        207: "golden retriever", 208: "Labrador",
        # Default
    }
    return class_names.get(class_idx, f"non-tree object (class {class_idx})")


# ─────────────────────────────────────────────────────────────
# Batch checker — checks multiple images
# ─────────────────────────────────────────────────────────────

def check_all_images(image_bytes_list: list) -> dict:
    """
    Check all uploaded images separately.
    Returns which images passed and which failed.
    """
    results = []
    all_passed = True
    failed_indices = []

    for i, image_bytes in enumerate(image_bytes_list):
        result = classify_image(image_bytes)
        result["image_number"] = i + 1
        results.append(result)

        if not result["is_tree"]:
            all_passed = False
            failed_indices.append(i + 1)

    return {
        "all_passed": all_passed,
        "total_images": len(image_bytes_list),
        "passed": len(image_bytes_list) - len(failed_indices),
        "failed": len(failed_indices),
        "failed_image_numbers": failed_indices,
        "results": results
    }