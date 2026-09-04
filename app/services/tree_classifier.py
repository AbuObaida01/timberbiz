import io
import torch
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image
from fastapi import HTTPException

# ImageNet class labels for tree-related categories
# These are ImageNet classes that represent trees/plants/nature
TREE_RELATED_CLASSES = {
    # Trees and plants
    340, 341, 342, 343, 344, 345, 346, 347, 348, 349,
    # Palms, ferns, mushrooms
    907, 992, 993, 994, 995, 996, 997, 998, 999,
    # Flowers and plants
    985, 986, 987, 988, 989, 990, 991,
    # Forest/nature scenes  
    972, 973, 974, 975, 976, 977, 978, 979, 980,
}

# Load model once when server starts
print("🌲 Loading tree classifier model...")
_model = None

def get_model():
    global _model
    if _model is None:
        # Use MobileNetV2 — lightweight, fast, accurate enough
        _model = models.mobilenet_v2(
            weights=models.MobileNet_V2_Weights.IMAGENET1K_V1
        )
        _model.eval()
        print("✅ Tree classifier model loaded")
    return _model

# Image preprocessing
transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

def classify_tree_image(image_bytes: bytes) -> dict:
    """
    Classify whether an image contains a tree or plant.
    Returns dict with is_tree, confidence, and class_label.
    """
    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

        # Preprocess
        tensor = transform(image).unsqueeze(0)

        # Run inference
        model = get_model()
        with torch.no_grad():
            outputs = model(tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)

        # Get top 5 predictions
        top5_prob, top5_idx = torch.topk(probabilities, 5)

        # Check if any top prediction is tree-related
        is_tree = False
        max_tree_confidence = 0.0
        detected_class = "Unknown"

        for prob, idx in zip(top5_prob, top5_idx):
            class_idx = idx.item()
            confidence = prob.item()

            if class_idx in TREE_RELATED_CLASSES:
                is_tree = True
                if confidence > max_tree_confidence:
                    max_tree_confidence = confidence
                    detected_class = f"Plant/Tree (class {class_idx})"

        # Also check top-1 prediction confidence
        top1_confidence = top5_prob[0].item()
        top1_class = top5_idx[0].item()

        # If top prediction is strongly non-tree (like a person, car, etc.)
        # and confidence is very high, it's definitely not a tree
        NON_TREE_HIGH_CONFIDENCE = 0.85
        if not is_tree and top1_confidence > NON_TREE_HIGH_CONFIDENCE:
            is_tree = False
            max_tree_confidence = 0.0

        # If model is uncertain (low confidence all around), give benefit of doubt
        if top1_confidence < 0.3:
            is_tree = True
            max_tree_confidence = 0.5
            detected_class = "Uncertain — allowed"

        return {
            "is_tree": is_tree,
            "confidence": round(max_tree_confidence * 100, 1),
            "detected_class": detected_class,
            "top_confidence": round(top1_confidence * 100, 1),
        }

    except Exception as e:
        # If classification fails, allow the upload
        # Better to allow than to block legitimate uploads due to bugs
        print(f"⚠️ Classifier error: {e}")
        return {
            "is_tree": True,
            "confidence": 0.0,
            "detected_class": "Classification failed — allowed",
            "top_confidence": 0.0,
        }