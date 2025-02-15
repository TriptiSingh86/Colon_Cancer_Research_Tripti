import numpy as np
import timm
import torch
import torchvision
from torchvision import datasets, models, transforms
import torch.utils.data as data
from torch.utils.tensorboard import SummaryWriter
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from nets import *
import time, os, copy, argparse
import multiprocessing
from torchsummary import summary
from matplotlib import pyplot as plt
#import torchvision.models as models
from torchvision.models import alexnet
from PIL import Image
#from ghostnet import ghostnet
from tensorflow.keras.preprocessing import image

# Construct argument parser
ap = argparse.ArgumentParser()
ap.add_argument("--mode", required=True, help="Training mode: finetue/transfer/scratch")
args= vars(ap.parse_args())

# Set training mode
train_mode=args["mode"]

# Set the train and validation directory paths 
train_directory = '/home/tripti/Documents/asliDataset/dataset/train'
valid_directory = '/home/tripti/Documents/asliDataset/dataset/val'
# Set the model save path
PATH="/home/tripti/Documents/asliCheckpoint/model.pth" 

if torch.cuda.is_available():
    print("GPU is available")
else:
    print("GPU is not available")
# Batch size
bs = 20
# Number of epochs
num_epochs = 10
# Number of classes
num_classes = 8
# Number of workers
num_cpu = multiprocessing.cpu_count()

# Applying transforms to the data
image_transforms = { 
    'train': transforms.Compose([
        transforms.RandomResizedCrop(size=256, scale=(0.8, 1.0)),
        transforms.RandomRotation(degrees=15),
        transforms.RandomHorizontalFlip(),
        #transforms.CenterCrop(size=256),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ]),
    'valid': transforms.Compose([
        transforms.Resize(size=256),
        #transforms.CenterCrop(size=256),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])
}
 
# Load data from folders
dataset = {
    'train': datasets.ImageFolder(root=train_directory, transform=image_transforms['train']),
    'valid': datasets.ImageFolder(root=valid_directory, transform=image_transforms['valid'])
}
 
# Size of train and validation data
dataset_sizes = {
    'train':len(dataset['train']),
    'valid':len(dataset['valid'])
}

# Create iterators for data loading
dataloaders = {
    'train':data.DataLoader(dataset['train'], batch_size=bs, shuffle=True,
                            num_workers=num_cpu, pin_memory=True, drop_last=True),
    'valid':data.DataLoader(dataset['valid'], batch_size=bs, shuffle=True,
                            num_workers=num_cpu, pin_memory=True, drop_last=True)
}

# Class names or target labels
class_names = dataset['train'].classes
print("Classes:", class_names)
 
# Print the train and validation data sizes
print("Training-set size:",dataset_sizes['train'],
      "\nValidation-set size:", dataset_sizes['valid'])

# Set default device as gpu, if available
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Load a pretrained model - Resnet18
print("\nLoading MobileNetV2 for finetuning ...\n")
#model_ft = models.shufflenet_v2_x1_0(pretrained=True)
#model_ft = models.efficientnet_b1(pretrained=True)

model_ft = timm.create_model('tf_efficientnet_b1', pretrained=True)

# Modify fc layers to match num_classes
num_ftrs = model_ft.classifier.in_features
model_ft.fc = nn.Linear(num_ftrs,num_classes )
model_ft= model_ft.to(device)
    # Set number of epochs to a higher value
num_epochs=100


# Transfer the model to GPU
#model_ft = model_ft.to(device)

# Print model summary
#print('Model Summary:-\n')
# for num, (name, param) in enumerate(model_ft.named_parameters()):
#     print(num, name, param.requires_grad )
# summary(model_ft, input_size=(3, 256, 256))
# print(model_ft)

# Loss function
criterion = nn.CrossEntropyLoss()

# Optimizer 
optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.01, momentum=0.9)

# Learning rate decay
exp_lr_scheduler = lr_scheduler.StepLR(optimizer_ft, step_size=7, gamma=0.1)

# Model training routine 
print("\nTraining:-\n")
def train_model(model, criterion, optimizer, scheduler, num_epochs=25):
    since = time.time()

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    # Tensorboard summary
    writer = SummaryWriter()
    print('num_epochs **** =', num_epochs )
    for epoch in range(num_epochs):
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train', 'valid']:
            if phase == 'train':
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluate mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data.
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device, non_blocking=True)
                labels = labels.to(device, non_blocking=True)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    # backward + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # statistics
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
            if phase == 'train':
                scheduler.step()

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc))

            # Record training loss and accuracy for each phase
            if phase == 'train':
                writer.add_scalar('Train/Loss', epoch_loss, epoch)
                writer.add_scalar('Train/Accuracy', epoch_acc, epoch)
                writer.flush()
            else:
                writer.add_scalar('Valid/Loss', epoch_loss, epoch)
                writer.add_scalar('Valid/Accuracy', epoch_acc, epoch)
                writer.flush()

            # deep copy the model
            if phase == 'valid' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

        print()

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:4f}'.format(best_acc))

    # load best model weights
    model.load_state_dict(best_model_wts)
    return model

# Train the model
model_ft = train_model(model_ft, criterion, optimizer_ft, exp_lr_scheduler,
                       num_epochs=num_epochs)
# Save the entire model
print("\nSaving the model...")
torch.save(model_ft, PATH)

'''
Sample run: python train.py --mode=finetue
'''
