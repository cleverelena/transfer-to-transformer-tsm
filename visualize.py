import numpy as np
import os
import argparse
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from sklearn import manifold
from sklearn.metrics import classification_report
from model import FCN, NonLinearClassifier, DilatedConvolution, Classifier
from tsm_utils import load_data, transfer_labels
from data import normalize_per_series
import torch
import tqdm
import torch.nn
from sklearn.manifold import MDS, TSNE
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

os.environ["CUDA_VISIBLE_DEVICES"] = '0'
DEVICE = torch.device('cuda:0' if torch.cuda.is_available() else "cpu")




def t_sne(xs, ys, seed=42):
    model = FCN(2).to(DEVICE)
    classifier = Classifier(128, 2).to(DEVICE)

    tsne = MDS(n_components=2, random_state=seed)
    xs_out = tsne.fit_transform(xs, ys)
    plt.subplot(2, 1, 1)
    plt.title('timeseries (seed '+ str(seed)+')')
    plt.scatter(xs_out[:,0], xs_out[:,1], c=ys)

    xs = torch.from_numpy(xs).to(DEVICE)
    xs = torch.unsqueeze(xs, 1)
    model.load_state_dict(torch.load('./visuals/Wine/direct_fcn_encoder.pt',map_location='cuda:0'))
    classifier.load_state_dict(torch.load('./visuals/Wine/direct_fcn_classifier.pt',map_location='cuda:0'))#,map_location=torch.device('cpu')))

    features, _ = model(xs, vis=True)
    feature_map = tsne.fit_transform(features.cpu().detach().numpy())
    plt.subplot(2, 1, 2)
    plt.title('feature map (seed '+ str(seed)+')')
    plt.scatter(feature_map[:,0], feature_map[:,1], c=ys)

    plt.tight_layout()
    plt.savefig('./visuals/tsne_seed_'+str(seed)+'.png')
    plt.savefig('./visuals/tsne_seed_'+str(seed)+'.pdf')

    plt.clf()



def heatmap(xs):
    model = FCN(2)
    model.eval()
    model.to(DEVICE)

    ts1 = plt.subplot2grid((2, 15), loc=(0, 0), colspan=4, rowspan=1)
    hm1 = plt.subplot2grid((2, 15), loc=(1, 0), colspan=4)
    ts2 = plt.subplot2grid((2, 15), loc=(0, 5), colspan=4, rowspan=1)
    hm2 = plt.subplot2grid((2, 15), loc=(1, 5), colspan=4)
    ts3 = plt.subplot2grid((2, 15), loc=(0, 10), colspan=4, rowspan=1)
    hm3 = plt.subplot2grid((2, 15), loc=(1, 10), colspan=4)

    x1 = xs[np.random.randint(0, xs.shape[0])]
    x_copy = x1
    # direct cls
    model.load_state_dict(torch.load('./visuals/Wine/direct_fcn_encoder.pt',map_location='cuda:0'))
    ts1.set_title('direct cls')
    ts1.plot(range(x_copy.shape[0]), x_copy)
    x1 = torch.from_numpy(x1).to(DEVICE)
    x1 = torch.unsqueeze(x1, 0)
    x1 = torch.unsqueeze(x1, 0)
    gaps, feature = model(x1, vis=True)
    gaps = torch.squeeze(gaps)
    feature = torch.squeeze(feature)
    feature = feature[torch.topk((gaps-gaps.mean())**2, k=16).indices,:].cpu()
    hm1.pcolormesh(feature[0:16],shading='nearest')

    # supervised transfer
    model.load_state_dict(torch.load('./visuals/Wine/encoder_NonInvasiveFetalECGThorax1_linear.pt',map_location='cuda:0'))
    ts2.set_title('positive transfer')
    ts2.plot(range(x_copy.shape[0]), x_copy)
    gaps, feature = model(x1, vis=True)
    gaps = torch.squeeze(gaps)
    feature = torch.squeeze(feature)
    feature = feature[torch.topk((gaps-gaps.mean())**2, k=16).indices,:].cpu()
    hm2.pcolormesh(feature[0:16],shading='nearest')

    model.load_state_dict(torch.load('./visuals/Wine/encoder_Crop_linear.pt',map_location='cuda:0'))
    ts3.set_title('negative transfer')
    ts3.plot(range(x_copy.shape[0]), x_copy)
    gaps, feature = model(x1, vis=True)
    gaps = torch.squeeze(gaps)
    feature = torch.squeeze(feature)
    feature = feature[torch.topk((gaps-gaps.mean())**2, k=16).indices,:].cpu()
    hm3.pcolormesh(feature[0:16],shading='nearest')
    

    plt.subplots_adjust(left=None,bottom=None,right=None,top=None,wspace=0.15,hspace=0.30)
    #plt.tight_layout()
    plt.savefig('./visuals/Wine_postive_negative.png')
    plt.savefig('./visuals/Wine_postive_negative.pdf')

def multi_cam(xs, ys):
    # sampling
    x0s = xs[np.where(ys==0)]
    x1s = xs[np.where(ys==1)]

    x0_mean = np.mean(x0s, axis=1)
    x0_mean_mean = np.mean(x0_mean, axis=0)
    class0 = x0s[np.where(np.abs(x0_mean-x0_mean_mean) == min(np.abs(x0_mean-x0_mean_mean)))]
    #class0 = np.expand_dims(class0, 0)
    print(class0.shape)

    x1_mean = np.mean(x1s, axis=1)
    x1_mean_mean = np.mean(x1_mean, axis=0)
    class1 = x1s[np.where(np.abs(x1_mean-x1_mean_mean) == min(np.abs(x1_mean-x1_mean_mean)))][0]
    class1= np.expand_dims(class1, 0)
    print(class1.shape)

    print(class0.mean())
    print(class1.mean())
    model = FCN(2).to(DEVICE)
    classifier = Classifier(128, 2).to(DEVICE)

    def cam(x, label):
        x = torch.from_numpy(x).to(DEVICE)
        #x = torch.unsqueeze(x, 0)
        x = torch.unsqueeze(x, 0)
        features, vis_out = model(x, vis=True)
        pred = classifier(features)

        w_k_c = classifier.state_dict()['dense.weight']
        cas = np.zeros(dtype=np.float16, shape=(vis_out.shape[2]))
        for k, w in enumerate(w_k_c[label,:]):
            cas += (w * vis_out[0, k, :]).cpu().numpy()
        
        minimum = np.min(cas)
        print(cas)
        cas = cas - minimum
        cas = cas / max(cas)
        cas = cas * 100
        
        x = x.cpu().numpy()
        plt_x = np.linspace(0, x.shape[2]-1, 2000, endpoint=True)

        f = interp1d(range(x.shape[2]), x.squeeze())
        y = f(plt_x)

        f = interp1d(range(x.shape[2]), cas)
        cas = f(plt_x).astype(int)
        
        plt.scatter(x=plt_x, y=y, c=cas, cmap='jet', marker='.',s=2, vmin=0, vmax=100, linewidths=1.0)
        
        plt.yticks([-1.0, 0.0, 1.0])

    plt.figure()
    
    model.load_state_dict(torch.load('./visuals/GunPoint/direct_fcn_encoder.pt',map_location='cuda:0'))
    classifier.load_state_dict(torch.load('./visuals/GunPoint/direct_fcn_classifier.pt',map_location='cuda:0'))
    plt.subplot(3, 1, 1)
    plt.title('Direct Classification')
    cam(class0, 0)
    cam(class1, 1)

   
    model.load_state_dict(torch.load('./visuals/GunPoint/supervised_encoder_UWaveGestureLibraryX_linear.pt',map_location='cuda:0'))
    classifier.load_state_dict(torch.load('./visuals/GunPoint/supervised_classifier_UWaveGestureLibraryX_linear.pt',map_location='cuda:0'))
    plt.subplot(3, 1, 2)
    plt.title('Supervised Transfer')
    cam(class0, 0)
    cam(class1, 1)

    
    model.load_state_dict(torch.load('./visuals/GunPoint/unsupervised_encoder_UWaveGestureLibraryX_linear.pt',map_location='cuda:0'))
    classifier.load_state_dict(torch.load('./visuals/GunPoint/unsupervised_classifier_UWaveGestureLibraryX_linear.pt',map_location='cuda:0'))
    plt.subplot(3, 1, 3)
    plt.title('Unsupervised Transfer')
    cam(class0, 0)
    cam(class1, 1)
    
    #plt.subplots_adjust(left=None,bottom=None,right=None,top=None,wspace=0.30,hspace=1.0)
    plt.tight_layout()
    plt.savefig('./visuals/fcn-supervised-unsupervised.png')
    plt.savefig('./visuals/fcn-supervised-unsupervised.pdf')



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataroot', type=str, default='/dev_data/zzj/hzy/datasets/UCR', help='data root')
    parser.add_argument('--dataset', type=str, default='GunPoint', help='dataset name')
    parser.add_argument('--backbone', type=str, choices=['dilated', 'fcn'], default='fcn', help='encoder backbone')
    parser.add_argument('--graph', type=str, choices=['cam', 'heatmap', 'tsne'], default='cam')

    args = parser.parse_args()
    
    xs, ys, num_classes = load_data(args.dataroot, args.dataset)
    xs = normalize_per_series(xs)
    ys = transfer_labels(ys)

    if args.graph == 'cam':
        multi_cam(xs, ys)
    elif args.graph == 'heatmap':
        heatmap(xs)
    elif args.graph == 'tsne':
        t_sne(xs, ys)

    
   