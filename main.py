import torch 
import torch.nn as nn
import torch.optim as optim
from model import FC, Discriminator, Loss_dis
from tqdm import tqdm
import os
from scipy import io
import numpy as np
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader
from torch.utils.data import TensorDataset

## data load

path = r'../DEAP/data_preprocessed_matlab/'  # 경로는 저장 파일 경로
file_list = os.listdir(path)

print("data path check")
for i in file_list:    # 확인
    print(i, end=' ')


for i in tqdm(file_list, desc="read data"): 
    mat_file = io.loadmat(path+i)
    data = mat_file['data']
    labels = np.array(mat_file['labels'])
    val = labels.T[0].round().astype(np.int8)
    aro = labels.T[1].round().astype(np.int8)
    
    if(i=="s01.mat"): 
        Data = data
        VAL = val
        ARO = aro
        continue
        
    Data = np.concatenate((Data ,data),axis=0)   # 밑으로 쌓아서 하나로 만듬
    VAL = np.concatenate((VAL ,val),axis=0)
    ARO = np.concatenate((ARO ,aro),axis=0)


# eeg preprocessing

eeg_data = []
peripheral_data = []

for i in tqdm(range(len(Data)), desc="preprocess channel"):
    for j in range (40): 
        if(j < 32): # get channels 1 to 32
            eeg_data.append(Data[i][j])
        else:
            peripheral_data.append(Data[i][j])

# set data type, shape
eeg_data = np.reshape(eeg_data, (len(Data),1,32, 8064))
eeg_data=eeg_data.astype('float32')
eeg_data32 = torch.from_numpy(eeg_data)
VAL = (torch.from_numpy(VAL)).type(torch.long)

# data split
print("data split")
x_train, x_test, y_train, y_test = train_test_split(eeg_data32, VAL, test_size=0.5)

# make data loader
print("make data loader")
target_dataset = TensorDataset(x_train, y_train)
source_dataset = TensorDataset(x_test, y_test)
target_dataloader = DataLoader(target_dataset, 64, shuffle=True)
source_dataloader = DataLoader(source_dataset, 64, shuffle=True)

# cuda
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
print("device: ", device)

#model
dis = Discriminator(15960)
fc = FC(32)

#optim
optimizer_dis = optim.SGD(dis.parameters(), lr=0.001, momentum=0.9)
optimizer_cls = optim.SGD(fc.parameters(), lr=0.001, momentum=0.9)
criterion = nn.CrossEntropyLoss()

#train
# At each iteration, we first update the parameters of the domain discriminator,\
# fix the feature extractor and classifier, and then fix the
#  domain discriminator and update the parameters of both the
#   feature extractor and classifier.
nb_epochs = 3
for epoch in tqdm(nb_epochs+1):
    temp_gloss = 0
    temp_dloss = 0
    temp_accuracy_d = 0
    temp_accuracy_s = 0
    g_loss_log = []
    d_loss_log = []
    accuracy_s = []
    accuracy_d = []
    print(i, ": epoch")

    for i, (target, source) in enumerate(zip(target_dataloader, source_dataloader)):
        
        #print(i, target[0].shape, target[1].shape)
        #print(source[0].shape, source[1].shape)
        x_target, y_target = target[0], target[1]
        x_source, y_source = source[0], source[1]

        x_target.to(device)
        y_target.to(device)
        x_source.to(device)
        y_source.to(device)
        
        feat_t, pred_t = fc.forward(x_target)
        feat_s, pred_s = fc.forward(x_source)
        
        dc_t = dis(feat_t)
        dc_s = dis(feat_s)
        temp_dc_s = dc_s.clone().detach()

        #discriminators loss
        dis_loss = Loss_dis(dc_t, dc_s)
        
       
        for p in fc.parameters():
            p.requires_grad = False
        for p in dis.parameters():
            p.requires_grad = True

        optimizer_dis.zero_grad()
        dis_loss.backward(retain_graph=True)
        optimizer_dis.step()
    
        for p in fc.parameters():
            p.requires_grad = True   
        for p in dis.parameters():
            p.requires_grad = False

        #global loss
        g_loss_adv = torch.mean(torch.square(temp_dc_s-1))/2
        g_loss_ce_t = criterion(pred_t, y_target-1)
        g_loss_ce_s = criterion(pred_s, y_source-1)
        g_loss = g_loss_adv + g_loss_ce_s + g_loss_ce_t
         
        optimizer_cls.zero_grad()
        g_loss.backward()
        optimizer_cls.step()
        
        temp_gloss += g_loss
        temp_dloss += dis_loss
        temp_accuracy_s += ((torch.argmax(pred_t,1)+1)== y_target).to(torch.float).mean()
        temp_accuracy_d += ((torch.argmax(pred_s,1)+1)== y_source).to(torch.float).mean()
    
    print("gloss", temp_gloss)
    print("dloss", temp_dloss)
    print("acc_d", temp_accuracy_d)
    print("acc_s", temp_accuracy_s)
    
    g_loss_log.append(temp_gloss)
    d_loss_log.append(temp_dloss)
    accuracy_d.append(temp_accuracy_d)
    accuracy_s.append(temp_accuracy_s)
        
    
        #python PROJECT\drda\drda_torch\main.py


torch.save(fc, './fc.pt')
torch.save(dis, './dis.pt')  