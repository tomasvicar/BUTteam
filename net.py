import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.nn import init
import matplotlib.pyplot as plt
import os







class myConv(nn.Module):
    def __init__(self, in_size, out_size,filter_size=3,stride=1,pad=None,do_batch=1,dov=0):
        super().__init__()
        
        pad=int((filter_size-1)/2)
        
        self.do_batch=do_batch
        self.dov=dov
        self.conv=nn.Conv1d(in_size, out_size,filter_size,stride,pad)
        self.bn=nn.BatchNorm1d(out_size,momentum=0.1)
        
        
        if self.dov>0:
            self.do=nn.Dropout(dov)
            
    def swish(self,x):
        return x * F.sigmoid(x)
    
    def forward(self, inputs):
     
        outputs = self.conv(inputs)
        if self.do_batch:
            outputs = self.bn(outputs)  
        
        # outputs=F.relu(outputs)
        outputs=self.swish(outputs)
        
        
        if self.dov>0:
            outputs = self.do(outputs)
        
        return outputs


        
class Net_addition_grow(nn.Module):
    def set_ts(self,ts):
        self.ts=ts
        
    def get_ts(self):
        return self.ts
    
    
    def __init__(self, levels=7,lvl1_size=4,input_size=12,output_size=9,convs_in_layer=3,init_conv=4,filter_size=13):
        super().__init__()
        self.levels=levels
        self.lvl1_size=lvl1_size
        self.input_size=input_size
        self.output_size=output_size
        self.convs_in_layer=convs_in_layer
        self.filter_size=filter_size
        
        
        
        self.init_conv=myConv(input_size,init_conv,filter_size=filter_size)
        
        
        self.layers=nn.ModuleList()
        for lvl_num in range(self.levels):
            
            
            if lvl_num==0:
                self.layers.append(myConv(init_conv, int(lvl1_size*(lvl_num+1)),filter_size=filter_size))
            else:
                self.layers.append(myConv(int(lvl1_size*(lvl_num))+int(lvl1_size*(lvl_num))+init_conv, int(lvl1_size*(lvl_num+1)),filter_size=filter_size))
            
            for conv_num_in_lvl in range(self.convs_in_layer-1):
                self.layers.append(myConv(int(lvl1_size*(lvl_num+1)), int(lvl1_size*(lvl_num+1)),filter_size=filter_size))


        self.conv_final=myConv(int(lvl1_size*(self.levels))+int(lvl1_size*(self.levels))+init_conv, int(lvl1_size*self.levels),filter_size=filter_size)
        
        self.fc=nn.Linear(int(lvl1_size*self.levels), self.output_size)
        
        
        
        
        ## weigths initialization wih xavier method
        for i, m in enumerate(self.modules()):
            if isinstance(m, nn.Conv2d):
                init.xavier_normal_(m.weight)
                init.constant_(m.bias, 0)
        
        
        
    def forward(self, x,lens):
        
        
        ## make signal len be divisible by 2**number of levels 
        ## replace rest by zeros
        for signal_num in range(list(x.size())[0]):
            
            k=int(np.floor(lens[signal_num].cpu().numpy()/(2**(self.levels-1)))*(2**(self.levels-1)))
            
            x[signal_num,:,k:]=0
        

        ## pad with more zeros  -  add as many zeros as convolution of all layers can proppagete numbers
        n=(self.filter_size-1)/2
        padded_length=n
        for p in range(self.levels):
            for c in range(self.convs_in_layer):
                padded_length=padded_length+2**p*n
        padded_length=padded_length+2**p*n+256 # 256 for sure

        
        shape=list(x.size())
        xx=torch.zeros((shape[0],shape[1],int(padded_length)),dtype=x.dtype)
        cuda_check = x.is_cuda
        if cuda_check:
            cuda_device = x.get_device()
            device = torch.device('cuda:' + str(cuda_device) )
            xx=xx.to(device)
        
        x=torch.cat((x,xx),2)### add zeros to signal
        
        x.requires_grad=True
        
        
        x=self.init_conv(x)
        
        x0=x
        
        ## aply all convolutions
        layer_num=-1
        for lvl_num in range(self.levels):
            
            
            for conv_num_in_lvl in range(self.convs_in_layer):
                layer_num+=1
                if conv_num_in_lvl==1:
                    y=x
                
                x=self.layers[layer_num](x)
                
            ## skip conection to previous layer and to the input
            x=torch.cat((F.avg_pool1d(x0,2**lvl_num,2**lvl_num),x,y),1)
            
            x=F.max_pool1d(x, 2, 2)
            
            
            
        x=self.conv_final(x)
        
        ### replace padded parts of signals by -inf => it will be not used in poolig
        for signal_num in range(list(x.size())[0]):
            
            k=int(np.floor(lens[signal_num].cpu().numpy()/(2**(self.levels-1))))
            
            x[signal_num,:,k:]=-np.Inf
            
        
        
        x=F.adaptive_max_pool1d(x,1)
        
        
        # N,C,1
        
        x=x.view(list(x.size())[:2])
        
        # N,C
        
        x=self.fc(x)
        
        x=torch.sigmoid(x)
        
        return x   
    
    def save_log(self,log):
        self.log=log
        
    def save_config(self,config):  
        self.config=config
        
    def save_lens(self,lens):
        self.lens=lens
        
    def save_train_names(self,train_names):
        
        tmp=[]
        for name in train_names['train']:
            path,filename = os.path.split(name)
            tmp.append(filename)
        train_names['train']=tmp
        
        tmp=[]
        for name in train_names['valid']:
            path,filename = os.path.split(name)
            tmp.append(filename)
        train_names['valid']=tmp
        
        self.train_names=train_names
        
        
        
    def get_matrix(self):
        

        return np.array([[5.5543955e-02, 5.5683166e-04, 1.6240923e-04, 3.7122107e-04,
                3.8978213e-03, 1.7865015e-03, 3.4337949e-03, 1.0881418e-02,
                3.6658081e-03, 3.4801976e-04, 2.1345213e-03, 0.0000000e+00,
                2.1809239e-03, 1.1832672e-03, 2.9001648e-03, 2.7609568e-03,
                1.4152804e-03, 7.4244215e-04, 1.3456765e-03, 5.8235307e-03,
                1.4245609e-02, 2.0649172e-03, 5.1738936e-03, 1.5544883e-03],
               [5.5683166e-04, 8.0624580e-02, 7.4244215e-04, 9.2805269e-05,
                8.0508571e-03, 3.2249831e-03, 3.4337949e-03, 1.2250296e-02,
                2.8769635e-03, 8.3524745e-04, 2.3665344e-03, 9.2805269e-05,
                5.5683166e-04, 9.0485142e-04, 0.0000000e+00, 2.3665344e-03,
                1.5776897e-03, 1.6240922e-03, 4.6402634e-05, 3.9442242e-04,
                8.5844874e-04, 3.0161714e-04, 1.0556600e-02, 2.5521449e-03],
               [1.6240923e-04, 7.4244215e-04, 7.2852140e-03, 0.0000000e+00,
                3.7122107e-04, 2.5521449e-04, 1.1600659e-04, 9.2805270e-04,
                6.9603957e-05, 3.0161714e-04, 3.0161714e-04, 0.0000000e+00,
                2.5521449e-04, 1.3920791e-04, 2.3201317e-05, 6.0323428e-04,
                3.0161714e-04, 1.3920791e-04, 2.3201317e-05, 9.2805269e-05,
                1.1600659e-04, 2.5521449e-04, 1.6008909e-03, 4.8722766e-04],
               [3.7122107e-04, 9.2805269e-05, 0.0000000e+00, 6.6819796e-03,
                2.5521449e-04, 3.4801976e-04, 0.0000000e+00, 0.0000000e+00,
                4.6402634e-05, 2.3201317e-05, 2.3201317e-05, 0.0000000e+00,
                2.3201318e-04, 3.2481845e-04, 0.0000000e+00, 2.3201317e-05,
                0.0000000e+00, 0.0000000e+00, 0.0000000e+00, 2.3201317e-05,
                0.0000000e+00, 0.0000000e+00, 9.2805269e-05, 4.6402634e-05],
               [3.8978213e-03, 8.0508571e-03, 3.7122107e-04, 2.5521449e-04,
                7.1251243e-02, 2.5521449e-03, 3.9674253e-03, 7.4012205e-03,
                6.9603957e-05, 2.3201317e-05, 6.9603957e-05, 0.0000000e+00,
                2.9697686e-03, 6.9603953e-04, 6.4963690e-04, 3.0161714e-04,
                1.2992738e-03, 1.7400988e-03, 6.7283824e-04, 2.3433331e-03,
                8.4452797e-03, 2.1577226e-03, 1.7168975e-03, 1.1136633e-03],
               [1.7865015e-03, 3.2249831e-03, 2.5521449e-04, 3.4801976e-04,
                2.5521449e-03, 3.7377324e-02, 3.1553793e-03, 7.8884484e-03,
                4.6402634e-05, 9.2805269e-05, 3.2481845e-04, 4.6402634e-05,
                1.8561054e-03, 4.8722766e-04, 5.5683166e-04, 1.7633002e-03,
                1.0440593e-03, 1.7168975e-03, 1.6008909e-03, 2.4593398e-03,
                2.0254750e-02, 2.5289436e-03, 4.0834318e-03, 9.0485142e-04],
               [3.4337949e-03, 3.4337949e-03, 1.1600659e-04, 0.0000000e+00,
                3.9674253e-03, 3.1553793e-03, 4.1901581e-02, 3.2157026e-02,
                2.3201317e-05, 2.0881186e-04, 6.9603953e-04, 2.3201317e-05,
                2.2969304e-03, 3.0161714e-04, 1.4384817e-03, 9.0485142e-04,
                1.6008909e-03, 3.7122107e-04, 1.1136633e-03, 1.2296699e-03,
                2.8792836e-02, 2.4825409e-03, 3.9210226e-03, 9.7445532e-04],
               [1.0881418e-02, 1.2250296e-02, 9.2805270e-04, 0.0000000e+00,
                7.4012205e-03, 7.8884484e-03, 3.2157026e-02, 1.4120322e-01,
                9.3965335e-03, 1.2064686e-03, 5.7075243e-03, 1.6240923e-04,
                4.9650818e-03, 1.2528711e-03, 1.8793067e-03, 3.1089766e-03,
                3.4337949e-03, 0.0000000e+00, 4.8258742e-03, 7.4244216e-03,
                9.4011739e-02, 8.2132667e-03, 1.3317556e-02, 2.5521449e-03],
               [3.6658081e-03, 2.8769635e-03, 6.9603957e-05, 4.6402634e-05,
                6.9603957e-05, 4.6402634e-05, 2.3201317e-05, 9.3965335e-03,
                2.4152571e-02, 2.3201317e-05, 9.2805269e-05, 2.3201317e-05,
                9.2805270e-04, 2.5521449e-04, 3.7122107e-04, 1.3920791e-04,
                1.1600659e-04, 2.3201317e-05, 3.9442242e-04, 1.0440593e-03,
                8.6076893e-03, 1.2760725e-03, 2.3201318e-04, 5.3363031e-04],
               [3.4801976e-04, 8.3524745e-04, 3.0161714e-04, 2.3201317e-05,
                2.3201317e-05, 9.2805269e-05, 2.0881186e-04, 1.2064686e-03,
                2.3201317e-05, 1.2899932e-02, 4.1762373e-04, 2.3201317e-05,
                9.2805270e-04, 2.0881186e-04, 1.1600659e-04, 8.3524745e-04,
                9.2805269e-05, 4.6402634e-05, 3.7122107e-04, 1.3688777e-03,
                3.5730030e-03, 2.0185146e-03, 2.9697686e-03, 5.5683166e-04],
               [2.1345213e-03, 2.3665344e-03, 3.0161714e-04, 2.3201317e-05,
                6.9603957e-05, 3.2481845e-04, 6.9603953e-04, 5.7075243e-03,
                9.2805269e-05, 4.1762373e-04, 2.3131713e-02, 2.3201317e-05,
                9.9765672e-04, 2.0881186e-04, 5.3363031e-04, 8.1204611e-04,
                1.9257094e-03, 7.1924087e-04, 5.5683166e-04, 1.6240922e-03,
                1.3665576e-02, 1.2992738e-03, 3.7122108e-03, 1.0672606e-03],
               [0.0000000e+00, 9.2805269e-05, 0.0000000e+00, 0.0000000e+00,
                0.0000000e+00, 4.6402634e-05, 2.3201317e-05, 1.6240923e-04,
                2.3201317e-05, 2.3201317e-05, 2.3201317e-05, 6.9371941e-03,
                2.3201317e-05, 0.0000000e+00, 0.0000000e+00, 0.0000000e+00,
                0.0000000e+00, 6.9603957e-05, 0.0000000e+00, 4.6402634e-05,
                1.1600659e-04, 0.0000000e+00, 0.0000000e+00, 2.3201317e-05],
               [2.1809239e-03, 5.5683166e-04, 2.5521449e-04, 2.3201318e-04,
                2.9697686e-03, 1.8561054e-03, 2.2969304e-03, 4.9650818e-03,
                9.2805270e-04, 9.2805270e-04, 9.9765672e-04, 2.3201317e-05,
                4.5056958e-02, 9.7445532e-04, 5.5683166e-04, 2.2737291e-03,
                1.0672606e-03, 2.0881186e-04, 3.9442242e-04, 2.3433331e-03,
                8.9789098e-03, 3.4337949e-03, 5.6147189e-03, 1.7865015e-03],
               [1.1832672e-03, 9.0485142e-04, 1.3920791e-04, 3.2481845e-04,
                6.9603953e-04, 4.8722766e-04, 3.0161714e-04, 1.2528711e-03,
                2.5521449e-04, 2.0881186e-04, 2.0881186e-04, 0.0000000e+00,
                9.7445532e-04, 1.2783926e-02, 0.0000000e+00, 1.5776897e-03,
                3.7122107e-04, 1.6240923e-04, 1.6240923e-04, 6.7283824e-04,
                0.0000000e+00, 1.9025081e-03, 2.0417159e-03, 7.8884483e-04],
               [2.9001648e-03, 0.0000000e+00, 2.3201317e-05, 0.0000000e+00,
                6.4963690e-04, 5.5683166e-04, 1.4384817e-03, 1.8793067e-03,
                3.7122107e-04, 1.1600659e-04, 5.3363031e-04, 0.0000000e+00,
                5.5683166e-04, 0.0000000e+00, 7.8884484e-03, 0.0000000e+00,
                8.5844874e-04, 2.3201317e-05, 1.1600659e-04, 1.8561054e-04,
                7.4012205e-03, 3.0161714e-04, 1.7400988e-03, 3.9442242e-04],
               [2.7609568e-03, 2.3665344e-03, 6.0323428e-04, 2.3201317e-05,
                3.0161714e-04, 1.7633002e-03, 9.0485142e-04, 3.1089766e-03,
                1.3920791e-04, 8.3524745e-04, 8.1204611e-04, 0.0000000e+00,
                2.2737291e-03, 1.5776897e-03, 0.0000000e+00, 3.5103593e-02,
                2.5985476e-03, 4.1762373e-04, 8.5844874e-04, 2.4129371e-03,
                2.2273266e-03, 1.7400988e-03, 1.2087886e-02, 3.2481845e-03],
               [1.4152804e-03, 1.5776897e-03, 3.0161714e-04, 0.0000000e+00,
                1.2992738e-03, 1.0440593e-03, 1.6008909e-03, 3.4337949e-03,
                1.1600659e-04, 9.2805269e-05, 1.9257094e-03, 0.0000000e+00,
                1.0672606e-03, 3.7122107e-04, 8.5844874e-04, 2.5985476e-03,
                2.3502935e-02, 3.7122107e-04, 6.7283824e-04, 2.0417159e-03,
                1.0486996e-02, 1.6936962e-03, 1.0626203e-02, 3.2017818e-03],
               [7.4244215e-04, 1.6240922e-03, 1.3920791e-04, 0.0000000e+00,
                1.7400988e-03, 1.7168975e-03, 3.7122107e-04, 0.0000000e+00,
                2.3201317e-05, 4.6402634e-05, 7.1924087e-04, 6.9603957e-05,
                2.0881186e-04, 1.6240923e-04, 2.3201317e-05, 4.1762373e-04,
                3.7122107e-04, 9.9069625e-03, 5.5683166e-04, 2.3201318e-04,
                5.2434979e-03, 1.0672606e-03, 7.8884483e-04, 2.0881186e-04],
               [1.3456765e-03, 4.6402634e-05, 2.3201317e-05, 0.0000000e+00,
                6.7283824e-04, 1.6008909e-03, 1.1136633e-03, 4.8258742e-03,
                3.9442242e-04, 3.7122107e-04, 5.5683166e-04, 0.0000000e+00,
                3.9442242e-04, 1.6240923e-04, 1.1600659e-04, 8.5844874e-04,
                6.7283824e-04, 5.5683166e-04, 2.8769635e-02, 2.8537621e-03,
                9.9301636e-03, 0.0000000e+00, 3.0625740e-03, 6.2643556e-04],
               [5.8235307e-03, 3.9442242e-04, 9.2805269e-05, 2.3201317e-05,
                2.3433331e-03, 2.4593398e-03, 1.2296699e-03, 7.4244216e-03,
                1.0440593e-03, 1.3688777e-03, 1.6240922e-03, 4.6402634e-05,
                2.3433331e-03, 6.7283824e-04, 1.8561054e-04, 2.4129371e-03,
                2.0417159e-03, 2.3201318e-04, 2.8537621e-03, 5.4731909e-02,
                8.1900656e-03, 2.3201317e-05, 7.3780189e-03, 2.6449503e-03],
               [1.4245609e-02, 8.5844874e-04, 1.1600659e-04, 0.0000000e+00,
                8.4452797e-03, 2.0254750e-02, 2.8792836e-02, 9.4011739e-02,
                8.6076893e-03, 3.5730030e-03, 1.3665576e-02, 1.1600659e-04,
                8.9789098e-03, 0.0000000e+00, 7.4012205e-03, 2.2273266e-03,
                1.0486996e-02, 5.2434979e-03, 9.9301636e-03, 8.1900656e-03,
                4.8365468e-01, 5.4755108e-03, 4.1391149e-02, 5.1738936e-03],
               [2.0649172e-03, 3.0161714e-04, 2.5521449e-04, 0.0000000e+00,
                2.1577226e-03, 2.5289436e-03, 2.4825409e-03, 8.2132667e-03,
                1.2760725e-03, 2.0185146e-03, 1.2992738e-03, 0.0000000e+00,
                3.4337949e-03, 1.9025081e-03, 3.0161714e-04, 1.7400988e-03,
                1.6936962e-03, 1.0672606e-03, 0.0000000e+00, 2.3201317e-05,
                5.4755108e-03, 5.5729564e-02, 9.4893388e-03, 3.0161713e-03],
               [5.1738936e-03, 1.0556600e-02, 1.6008909e-03, 9.2805269e-05,
                1.7168975e-03, 4.0834318e-03, 3.9210226e-03, 1.3317556e-02,
                2.3201318e-04, 2.9697686e-03, 3.7122108e-03, 0.0000000e+00,
                5.6147189e-03, 2.0417159e-03, 1.7400988e-03, 1.2087886e-02,
                1.0626203e-02, 7.8884483e-04, 3.0625740e-03, 7.3780189e-03,
                4.1391149e-02, 9.4893388e-03, 1.0841976e-01, 9.5821442e-03],
               [1.5544883e-03, 2.5521449e-03, 4.8722766e-04, 4.6402634e-05,
                1.1136633e-03, 9.0485142e-04, 9.7445532e-04, 2.5521449e-03,
                5.3363031e-04, 5.5683166e-04, 1.0672606e-03, 2.3201317e-05,
                1.7865015e-03, 7.8884483e-04, 3.9442242e-04, 3.2481845e-03,
                3.2017818e-03, 2.0881186e-04, 6.2643556e-04, 2.6449503e-03,
                5.1738936e-03, 3.0161713e-03, 9.5821442e-03, 2.5799865e-02]],
              dtype=np.float32)

        
        
        
        
        