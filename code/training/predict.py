import cv2
import torch
import numpy as np
from torch.utils.data import DataLoader

FLIPS = [[-1], [-2], [-2, -1]]


def threshold_resize(preds, shape, threshold=0.5):

    preds = (preds > threshold).astype(np.uint8)

    preds = cv2.resize(
        preds,
        (shape[0], shape[1]),
        interpolation=cv2.INTER_AREA,
    )

    return preds


def threshold_resize_torch(preds, shape, threshold=0.5):
    preds = preds.unsqueeze(0).unsqueeze(0)
    preds = torch.nn.functional.interpolate(
        preds, (shape[1], shape[0]), mode='bilinear', align_corners=False
    )
    return (preds > threshold).cpu().numpy()[0, 0]


def get_tile_weighting(size, sigma=1, alpha=1, eps=1e-6):
    half = size // 2
    w = np.ones((size, size), np.float32)

    x = np.concatenate([np.mgrid[-half:0], np.mgrid[1: half + 1]])[:, None]
    x = np.tile(x, (1, size))
    x = half + 1 - np.abs(x)
    y = x.T

    w = np.minimum(x, y)
    w = (w / w.max()) ** sigma
    w = np.minimum(w, 1)

    w = (w - np.min(w) + eps) / (np.max(w) - np.min(w) + eps)

    w = np.where(w > alpha, 1, w)
    w = w / alpha
    w = np.clip(w, 1e-3, 1)

    w = np.round(w, 3)
    return w.astype(np.float16)


def predict_entire_mask_downscaled(dataset, model, batch_size=32, tta=False):

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, pin_memory=True)

    weighting = torch.from_numpy(get_tile_weighting(dataset.tile_size, sigma=1, alpha=1))
    weighting_cuda = weighting.clone().cuda().unsqueeze(0)
    weighting = weighting.cuda().half()

    global_pred = torch.zeros(
        (dataset.orig_size[0], dataset.orig_size[1]),
        dtype=torch.half, device="cuda"
    )
    global_counter = torch.zeros(
        (dataset.orig_size[0], dataset.orig_size[1]),
        dtype=torch.half, device="cuda"
    )

    model.eval()
    with torch.no_grad():
        for img, pos in loader:
            img = img.to("cuda")
            _, _, h, w = img.shape

            if model.num_classes == 2:
                pred = model(img)[:, 0].view(-1, h, w).sigmoid().detach()
            else:
                pred = model(img).view(-1, h, w).sigmoid().detach()

            if tta:
                for f in FLIPS:
                    pred_flip = model(torch.flip(img, f))
                    if model.num_classes == 2:
                        pred_flip = pred_flip[:, 0]
                    pred_flip = torch.flip(pred_flip, f).view(-1, h, w).sigmoid().detach()
                    pred += pred_flip
                pred = torch.div(pred, len(FLIPS) + 1)

            pred = (pred * weighting_cuda).half()

            for tile_idx, (x0, x1, y0, y1) in enumerate(pos):
                global_pred[x0: x1, y0: y1] += pred[tile_idx]
                global_counter[x0: x1, y0: y1] += weighting

    for i in range(len(global_pred)):
        global_pred[i] = torch.div(global_pred[i], global_counter[i])

    return global_pred


def predict_entire_mask(dataset, model, batch_size=32, tta=False):
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, pin_memory=True)

    weighting = torch.from_numpy(get_tile_weighting(dataset.tile_size, sigma=1, alpha=1))
    weighting_cuda = weighting.clone().cuda().unsqueeze(0)
    weighting = weighting.cuda().half()

    global_pred = torch.zeros(
        (dataset.orig_size[0], dataset.orig_size[1]),
        dtype=torch.half, device="cuda"
    )
    global_counter = torch.zeros(
        (dataset.orig_size[0], dataset.orig_size[1]),
        dtype=torch.half, device="cuda"
    )

    model.eval()
    with torch.no_grad():
        for img, pos in loader:
            img = img.to("cuda")
            _, _, h, w = img.shape

            if model.num_classes == 2:
                pred = model(img)[:, 0].view(-1, 1, h, w).sigmoid().detach()
            else:
                pred = model(img).view(-1, 1, h, w).sigmoid().detach()

            if tta:
                for f in FLIPS:
                    pred_flip = model(torch.flip(img, f))
                    if model.num_classes == 2:
                        pred_flip = pred_flip[:, 0]

                    pred_flip = torch.flip(pred_flip, f).view(-1, 1, h, w).sigmoid().detach()
                    pred += pred_flip
                pred = torch.div(pred, len(FLIPS) + 1)

            pred = torch.nn.functional.interpolate(
                pred, (dataset.tile_size, dataset.tile_size), mode='area'
            ).view(-1, dataset.tile_size, dataset.tile_size)

            pred = (pred * weighting_cuda).half()

            for tile_idx, (x0, x1, y0, y1) in enumerate(pos):
                global_pred[x0: x1, y0: y1] += pred[tile_idx]
                global_counter[x0: x1, y0: y1] += weighting

    for i in range(len(global_pred)):
        global_pred[i] = torch.div(global_pred[i], global_counter[i])

    return global_pred
