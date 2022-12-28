# -*- coding: utf-8 -*-
"""Training.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/14TngS7vSRj7gpFSKrymFo3_sriaxLMsF
"""

from google.colab import drive
drive.mount('/content/drive/')

# Commented out IPython magic to ensure Python compatibility.
# %cd drive/MyDrive/ExamProject

!ls

! unzip archive.zip

#install data augmentation library
!pip install -U albumentations

"""##1- import needed libraries """

import albumentations as A
import cv2
from albumentations.pytorch import ToTensorV2
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os
import random
import torch
from collections import Counter
from torch.utils.data import DataLoader
from tqdm import tqdm
from intersection_over_union import intersection_over_union , intersection_over_union_wh
from mean_average_precision import mean_average_precision
from non_max_suppression import nms
from YOLOV3_the_model import YOLOv3
from tqdm import tqdm
## import the utils
from yolov3_loss_function import Yolov3Loss
from yolo_dataset import YOLODataset

"""##2- define hyper and nessecery parameters"""

#to get some performance improvments
torch.backends.cudnn.benchmark = True
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
#the anchors that was calculated using k-means
ANCHORS = [
    [(0.28, 0.22), (0.38, 0.48), (0.9, 0.78)],
    [(0.07, 0.15), (0.15, 0.11), (0.14, 0.29)],
    [(0.02, 0.03), (0.04, 0.07), (0.08, 0.06)],
]  # Note these have been rescaled to be between [0, 1]
#this number of classes id for the pascal dataset for coco it is 80
NUM_CLASSES = 20
LEARNING_RATE = 1e-5
WEIGHT_DECAY = 1e-4
NUM_EPOCHS = 10
#if the probability of an object is greater than 0.05 then we say there is an objct
#in the bbx
CONF_THRESHOLD = 0.05
#this is used to calculate the mean average preciision
MAP_IOU_THRESH = 0.5
#the dataset
DATASET = 'PASCAL_VOC'

#check if we wanna load the dataset
PIN_MEMORY = True
LOAD_MODEL = False
SAVE_MODEL = True

#where we will save the models
CHECKPOINT_FILE = "checkpoint.pth.tar"
filename= "my_checkpoint.pth.tar"
IMG_DIR = DATASET + "/images/"
LABEL_DIR = DATASET + "/labels/"
NUM_WORKERS = 4
BATCH_SIZE = 32
IMAGE_SIZE = 416
#scaler to scale images
S = [IMAGE_SIZE // 32, IMAGE_SIZE // 16, IMAGE_SIZE // 8] #13 26 52
scale = 1.1
#pascal classes

PASCAL_CLASSES = [
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor"
]

train_transforms = A.Compose(
    [
        A.LongestMaxSize(max_size=int(IMAGE_SIZE * scale)),
        A.PadIfNeeded(
            min_height=int(IMAGE_SIZE * scale),
            min_width=int(IMAGE_SIZE * scale),
            border_mode=cv2.BORDER_CONSTANT,
        ),
        A.RandomCrop(width=IMAGE_SIZE, height=IMAGE_SIZE),
        A.ColorJitter(brightness=0.6, contrast=0.6, saturation=0.6, hue=0.6, p=0.4),
        A.OneOf(
            [
                A.ShiftScaleRotate(
                    rotate_limit=10, p=0.4, border_mode=cv2.BORDER_CONSTANT
                ),
                A.IAAAffine(shear=10, p=0.4, mode="constant"),
            ],
            p=1.0,
        ),
        A.HorizontalFlip(p=0.5),
        A.Blur(p=0.1),
        A.CLAHE(p=0.1),
        A.Posterize(p=0.1),
        A.ToGray(p=0.1),
        A.ChannelShuffle(p=0.05),
        A.Normalize(mean=[0, 0, 0], std=[1, 1, 1], max_pixel_value=255,),
        ToTensorV2(),
    ],
    bbox_params=A.BboxParams(format="yolo", min_visibility=0.4, label_fields=[],),
)
test_transforms = A.Compose(
    [
        A.LongestMaxSize(max_size=IMAGE_SIZE),
        A.PadIfNeeded(
            min_height=IMAGE_SIZE, min_width=IMAGE_SIZE, border_mode=cv2.BORDER_CONSTANT
        ),
        A.Normalize(mean=[0, 0, 0], std=[1, 1, 1], max_pixel_value=255,),
        ToTensorV2(),
    ],
    bbox_params=A.BboxParams(format="yolo", min_visibility=0.4, label_fields=[]),
)

def train(train_loader, model, optimazer, loss_fn, scaler, scaled_anchors  ):
    #this to get a prograss bar
    loop= tqdm(train_loader, leave=True)
    #we willstore the mean loss of each epoch
    losses= []
    
    for batch_inds, (x,y) in enumerate(loop):
        x= x.to(DEVICE)
        #x = torch.tensor(x.numpy().transpose(0, 3, 1,2))
        #since we have three different scales
        y0, y1, y2 =(
            y[0].to(DEVICE),
            y[1].to(DEVICE),
            y[2].to(DEVICE)
        )
        
        #to make everything float16 
        with torch.cuda.amp.autocast():
            out= model(x)
            loss=(
                #we pass the scaled_anchors because the output is gonna be dependent on the cell size 
                loss_fn(out[0], y0, scaled_anchors[0])
                +loss_fn(out[1], y1, scaled_anchors[1])
                +loss_fn(out[2], y2, scaled_anchors[2])
            )
            #append the losses
            losses.append(loss.item())
            optimazer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimazer)
            scaler.update()
            
            #updating the progress bar
            mean_loss= sum(losses)/len(losses)
            loop.set_postfix(loss= mean_loss)

def main():
    model= YOLOv3(num_classes=NUM_CLASSES).to(DEVICE)
    optimizer= torch.optim.Adam(
    model.parameters(), lr= LEARNING_RATE, weight_decay= WEIGHT_DECAY
    )
    loss_fn= Yolov3Loss()
    scaler= torch.cuda.amp.GradScaler()
    train_loader, test_loader, train_eval_loader= get_loaders(
      train_csv_path=DATASET+"/train.csv", test_csv_path= DATASET+"/test.csv"
    )
    
    if LOAD_MODEL:
        load_checkpoints(
        CHECKPOINT_FILE,model, optimizer, LEARNING_RATE
        )
        
    scaler_anchors= (
        #scaled anchores unsquize to make sure that it has the same number of dimentions
        #as the anchores 
        torch.tensor(ANCHORS)* torch.tensor(S).unsqueeze(1).unsqueeze(2).repeat(1,3,2)
    ).to(DEVICE)
    
    for epoch in range(NUM_EPOCHS):
        train(train_loader, model, optimizer, loss_fn, scaler, scaler_anchors)
    
    if SAVE_MODEL:
        save_checkpoint(model, optimizer)
        
    
    if epoch%10 ==0 and epoch>0:
        print("On Test Loader:")
        check_class_accuracy(model, test_loader, threshold = CONF_THRESHOLD)
        
        pred_boxes, true_boxes= get_evaluation_bboxes

def get_loaders(train_csv_path, test_csv_path):
    #from yolo_dataset import YOLODataset
    IMAGE_SIZE = 416
    train_dataset = YOLODataset(
        train_csv_path,
        transform=train_transforms,
        S=[IMAGE_SIZE // 32, IMAGE_SIZE // 16, IMAGE_SIZE // 8],
        img_dir=IMG_DIR,
        label_dir=LABEL_DIR,
        anchors=ANCHORS,
    )
    test_dataset = YOLODataset(
        test_csv_path,
        transform= test_transforms,
        S=[IMAGE_SIZE // 32, IMAGE_SIZE // 16, IMAGE_SIZE // 8],
        img_dir=IMG_DIR,
        label_dir=LABEL_DIR,
        anchors=ANCHORS,
    )
    
    #train_loader = DataLoader(dataset=train_dataset, batch_size=1, shuffle=True)
    train_loader = DataLoader(
        dataset=train_dataset,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
        shuffle=False,
        drop_last=False,
    )
    test_loader = DataLoader(
        dataset=test_dataset,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
        shuffle=False,
        drop_last=False,
    )

    train_eval_dataset = YOLODataset(
        train_csv_path,
        transform=test_transforms,
        S=[IMAGE_SIZE // 32, IMAGE_SIZE // 16, IMAGE_SIZE // 8],
        img_dir=IMG_DIR,
        label_dir=LABEL_DIR,
        anchors=ANCHORS,
    )
    train_eval_loader = DataLoader(
        dataset=train_eval_dataset,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        pin_memory=PIN_MEMORY,
        shuffle=False,
        drop_last=False,
    )

    return train_loader, test_loader, train_eval_loader

def check_class_accuracy(model, loader, threshold):
    model.eval()
    tot_class_preds, correct_class = 0, 0
    tot_noobj, correct_noobj = 0, 0
    tot_obj, correct_obj = 0, 0

    for idx, (x, y) in enumerate(tqdm(loader)):
        x = x.to(DEVICE)
        with torch.no_grad():
            out = model(x)

        for i in range(3):
            y[i] = y[i].to(DEVICE)
            obj = y[i][..., 0] == 1 # in paper this is Iobj_i
            noobj = y[i][..., 0] == 0  # in paper this is Iobj_i

            correct_class += torch.sum(
                torch.argmax(out[i][..., 5:][obj], dim=-1) == y[i][..., 5][obj]
            )
            tot_class_preds += torch.sum(obj)

            obj_preds = torch.sigmoid(out[i][..., 0]) > threshold
            correct_obj += torch.sum(obj_preds[obj] == y[i][..., 0][obj])
            tot_obj += torch.sum(obj)
            correct_noobj += torch.sum(obj_preds[noobj] == y[i][..., 0][noobj])
            tot_noobj += torch.sum(noobj)

    print(f"Class accuracy is: {(correct_class/(tot_class_preds+1e-16))*100:2f}%")
    print(f"No obj accuracy is: {(correct_noobj/(tot_noobj+1e-16))*100:2f}%")
    print(f"Obj accuracy is: {(correct_obj/(tot_obj+1e-16))*100:2f}%")
    model.train()

def cells_to_bboxes(predictions, anchors, S, is_preds=True):
    """
    Scales the predictions coming from the model to
    be relative to the entire image such that they for example later
    can be plotted or.
    INPUT:
    predictions: tensor of size (N, 3, S, S, num_classes+5)
    anchors: the anchors used for the predictions
    S: the number of cells the image is divided in on the width (and height)
    is_preds: whether the input is predictions or the true bounding boxes
    OUTPUT:
    converted_bboxes: the converted boxes of sizes (N, num_anchors, S, S, 1+5) with class index,
                      object score, bounding box coordinates
    """
    BATCH_SIZE = predictions.shape[0]
    num_anchors = len(anchors)
    box_predictions = predictions[..., 1:5]
    if is_preds:
        anchors = anchors.reshape(1, len(anchors), 1, 1, 2)
        box_predictions[..., 0:2] = torch.sigmoid(box_predictions[..., 0:2])
        box_predictions[..., 2:] = torch.exp(box_predictions[..., 2:]) * anchors
        scores = torch.sigmoid(predictions[..., 0:1])
        best_class = torch.argmax(predictions[..., 5:], dim=-1).unsqueeze(-1)
    else:
        scores = predictions[..., 0:1]
        best_class = predictions[..., 5:6]

    cell_indices = (
        torch.arange(S)
        .repeat(predictions.shape[0], 3, S, 1)
        .unsqueeze(-1)
        .to(predictions.device)
    )
    x = 1 / S * (box_predictions[..., 0:1] + cell_indices)
    y = 1 / S * (box_predictions[..., 1:2] + cell_indices.permute(0, 1, 3, 2, 4))
    w_h = 1 / S * box_predictions[..., 2:4]
    converted_bboxes = torch.cat((best_class, scores, x, y, w_h), dim=-1).reshape(BATCH_SIZE, num_anchors * S * S, 6)
    return converted_bboxes.tolist()

def get_evaluation_bboxes(
    loader,
    model,
    iou_threshold,
    anchors,
    threshold,
    box_format="midpoint",
    device="cuda",
):
    # make sure model is in eval before get bboxes
    model.eval()
    train_idx = 0
    all_pred_boxes = []
    all_true_boxes = []
    for batch_idx, (x, labels) in enumerate(tqdm(loader)):
        x = x.to(device)

        with torch.no_grad():
            predictions = model(x)

        batch_size = x.shape[0]
        bboxes = [[] for _ in range(batch_size)]
        for i in range(3):
            S = predictions[i].shape[2]
            anchor = torch.tensor([*anchors[i]]).to(device) * S
            boxes_scale_i = cells_to_bboxes(
                predictions[i], anchor, S=S, is_preds=True
            )
            for idx, (box) in enumerate(boxes_scale_i):
                bboxes[idx] += box

        # we just want one bbox for each label, not one for each scale
        true_bboxes = cells_to_bboxes(
            labels[2], anchor, S=S, is_preds=False
        )

        for idx in range(batch_size):
            nms_boxes = nms(
                bboxes[idx],
                iou_threshold=iou_threshold,
                threshold=threshold,
                box_format=box_format,
            )

            for nms_box in nms_boxes:
                all_pred_boxes.append([train_idx] + nms_box)

            for box in true_bboxes[idx]:
                if box[1] > threshold:
                    all_true_boxes.append([train_idx] + box)

            train_idx += 1

    model.train()
    return all_pred_boxes, all_true_boxes

if __name__=="__main__":
    main()

model= YOLOv3(num_classes=NUM_CLASSES).to(DEVICE)
optimizer= torch.optim.Adam(
model.parameters(), lr= LEARNING_RATE, weight_decay= WEIGHT_DECAY
)
loss_fn= Yolov3Loss()
scaler= torch.cuda.amp.GradScaler()
train_loader, test_loader, train_eval_loader= get_loaders(
  train_csv_path=DATASET+"/train.csv", test_csv_path= DATASET+"/test.csv"
)

if LOAD_MODEL:
    # load_checkpoints(
    # CHECKPOINT_FILE,model, optimizer, LEARNING_RATE
    # )
    print("=> Loading checkpoint")
    checkpoint = torch.load(CHECKPOINT_FILE, map_location=DEVICE)
    model.load_state_dict(checkpoint["state_dict"])
    optimizer.load_state_dict(checkpoint["optimizer"])

    # If we don't do this then it will just have learning rate of old checkpoint
    # and it will lead to many hours of debugging \:
    for param_group in optimizer.param_groups:
      param_group["lr"] = LEARNING_RATE
    
scaler_anchors= (
    #scaled anchores unsquize to make sure that it has the same number of dimentions
    #as the anchores 
    torch.tensor(ANCHORS)* torch.tensor(S).unsqueeze(1).unsqueeze(2).repeat(1,3,2)
).to(DEVICE)

for epoch in range(NUM_EPOCHS):
    train(train_loader, model, optimizer, loss_fn, scaler, scaler_anchors)

if SAVE_MODEL:
    #save_checkpoint(model, optimizer)
    print("=> Saving checkpoint")
    checkpoint = {
        "state_dict": model.state_dict(),
        "optimizer": optimizer.state_dict(),
    }
    torch.save(checkpoint, filename)
    

if epoch%10 ==0 and epoch>0:
    print("On Test Loader:")
    check_class_accuracy(model, test_loader, threshold = CONF_THRESHOLD)
    
    pred_boxes, true_boxes= get_evaluation_bboxes

model

!ls

checkpoint

torch.save(checkpoint, "/content/drive/MyDrive/my_checkpoint_nana.pth.tar")

!ls
