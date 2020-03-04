import numpy as np
import pandas as pd
from tqdm import tqdm
from glob import glob
from natsort import natsorted
import matplotlib.cm 
import matplotlib.pyplot as plt
import os
from .simulation import load_lookup_functions
from .utils import load





def reconstruct(folder, lookupfile, muperpixel, outfile=None, r_min=2):
    # get filepaths for PIV results
    dis_files = natsorted(glob(folder+'/dis*.npy'))
    seg_files = natsorted(glob(folder+'/seg*.npy'))

    # load lookup table
    get_displacement, get_pressure = load_lookup_functions(lookupfile)

    # initial spheroid radius and surface (used for force estimation)
    r0 = load(seg_files[0])['radius']
    A0 = 4 * np.pi * (r0 * (10 ** -6)) ** 2

    # initialize result dictionary
    results = {'pressure_mean': [], 'pressure_median': [], 'pressure_std': [],
               'contractility_mean': [], 'contractility_median': [], 'contractility_std': [],
               'pressure_min': [], 'pressure_max': [], 'contractility_min': [], 'contractility_max': [],
               'angle_min': [], 'angle_max': []}

    # create dict with all angles
    angles_dict = {str(a): [] for a in range(-180, 180, 5)}
    
    u_sum = None
    v_sum = None

    # loop over series of PIV results
    for (dis_file, seg_file) in tqdm(zip(dis_files, seg_files)):
        dis = load(dis_file)
        seg = load(seg_file)

        x_rav = np.ravel(dis['x'])
        y_rav = np.ravel(dis['y'])

        try:
            u_sum += np.ravel(dis['u'])
            v_sum += np.ravel(dis['v'])
        except:
            u_sum = np.ravel(dis['u'])
            v_sum = np.ravel(dis['v'])

        cx, cy = seg['centroid']

        distance, displacement, angle, pressure = infer_pressure(x_rav, y_rav, u_sum, v_sum, cx, cy, r0, get_pressure)
        mask = distance > r_min

        pr_angle = []
        pr_median = []
        for alpha in range(-180, 180, 5):
            mask2 = (angle >= (alpha-5)*np.pi/180.) & (angle < (alpha+5)*np.pi/180.)
            pr_angle.append(alpha)
            pr_median.append(np.nanmedian(pressure[mask & mask2]))

        i_min = np.nanargmin(pr_median)
        alpha_min = pr_angle[i_min]
        pressure_min = pr_median[i_min]

        i_max = np.nanargmax(pr_median)
        alpha_max = pr_angle[i_max]
        pressure_max = pr_median[i_max]

        pressure_mean = np.nanmean(pressure[mask])
        pressure_median = np.nanmedian(pressure[mask])
        pressure_std = np.nanstd(pressure[mask], ddof=1)

        contractility_mean = pressure_mean*A0*(muperpixel**2.)*(10**6)  # unit: µN
        contractility_median = pressure_median*A0*(muperpixel**2.)*(10**6)  # unit: µN
        contractility_std = pressure_std*A0*(muperpixel**2.)*(10**6)  # unit: µN

        contractility_min = pressure_min*A0*(muperpixel**2.)*(10**6)  # unit: µN
        contractility_max = pressure_max*A0*(muperpixel**2.)*(10**6)  # unit: µN

        results['pressure_mean'].append(pressure_mean)
        results['pressure_median'].append(pressure_median)
        results['pressure_std'].append(pressure_std)

        results['contractility_mean'].append(contractility_mean)
        results['contractility_median'].append(contractility_median)
        results['contractility_std'].append(contractility_std)

        results['pressure_min'].append(pressure_min)
        results['pressure_max'].append(pressure_max)

        results['contractility_min'].append(contractility_min)
        results['contractility_max'].append(contractility_max)

        results['angle_min'].append(alpha_min)
        results['angle_max'].append(alpha_max)
        
        # append pressures for all angle data
        for i,a in enumerate(angles_dict):
            angles_dict[a].append(pr_median[i])

    df = pd.DataFrame.from_dict(results)
    df.columns = ['Mean Pressure (Pa)',
                  'Median Pressure (Pa)',
                  'St.dev. Pressure (Pa)',
                  'Mean Contractility (µN)',
                  'Median Contractility (µN)',
                  'St.dev. Contractility (µN)',
                  'Minimal Median Pressure (Pa)',
                  'Maximal Median Pressure (Pa)',
                  'Minimal Median Contractility (µN)',
                  'Maximal Median Contractility (µN)',
                  'Angle of minimal Pr./Contr. (deg)',
                  'Angle of maximal Pr./Contr. (deg)']

    if outfile is not None:
        df.to_excel(outfile)
    else:
        df.to_excel(folder+'//result.xlsx')
     
    # save pressures for all angles
    an = pd.DataFrame.from_dict(angles_dict)
    an.columns = [a for a in range(-180, 180, 5)]
    if outfile is not None:
        an.to_excel(outfile[:-5]+'_angles.xlsx')
    else:
        an.to_excel(folder+'//result_angles.xlsx')    

    return df    
 



def infer_pressure(x_rav, y_rav, u_rav, v_rav, x_sph, y_sph, r_sph, get_pressure):
    dx = (x_rav[~np.isnan(u_rav)] - x_sph) / r_sph
    dy = (y_rav[~np.isnan(u_rav)] - y_sph) / r_sph
    distance = np.sqrt(dx ** 2 + dy ** 2)
    angle = np.arctan2(dy, dx)

    u_rav2 = u_rav[~np.isnan(u_rav)] / r_sph
    v_rav2 = v_rav[~np.isnan(u_rav)] / r_sph

    m = (np.array([dx, dy]).T) / np.expand_dims(distance, axis=1)
    d = np.array([u_rav2, v_rav2]).T

    displacement = np.array([-np.dot(di, mi) for di, mi in zip(d, m)])

    abs = np.sqrt(u_rav2**2. + v_rav2**2.)
    mask = displacement/abs > 0.94  # cos(20deg)

    distance = distance[mask]
    angle = angle[mask]
    displacement = displacement[mask]

    pressure = get_pressure(distance, displacement)

    return [distance, displacement, angle, pressure]


# Evaluate Angle dependet Pressures
def angle_analysis(folder, output, n_max=None, small_pressure = False, fontsize=7, name_of_resultfile='result_angles.xlsx', dt=None):
    """
    Evaluate angles over time for an spheroid (needs folder where 'reconstruct' function was used) and stores 
    the results in the output folder.
    - N_max may define the last image to evaluate 
    - Small_pressure true returns plots that are scaled to 100 Pa whereas false returns plots that are scaled up to 1000 Pa
    - Evaluated excel sheet with angle data is automatically searched in folder, if name differs from  'result_angles.xlsx' it can be specified using name_of_resultfile
    - dt is time between consecutive images in seconds; If given a timestamp will be displayed 
    """
    from datetime import timedelta
    
    # read in angle pressures
    angles  = pd.read_excel(folder + '//'+ name_of_resultfile)
    # read in plots
    plots = glob(folder+'//plot*.png')
    # make folder if not existing
    if not os.path.exists(output):
        os.makedirs(output)
    # list of evaluated angles
    angle_list = [a for a in range(-180, 180, 5)]
    # make figure
    f, (ax1, ax2) = plt.subplots(1, 2, figsize=(9,5))
            
    #second plot with only the left plot
    fb,axb = plt.subplots( figsize=(3,3))  
    # for color norm
    max_pr = np.nanmax([np.max(np.array(angles[z])[:n_max]) for z in angle_list])  
    plt.style.use('dark_background')
    
    # make result dictionary
    res_angles = {'mean_pr_angles (Pa)': [], 'sd_pr_angles (Pa)': [], 'CoV': []}
    
    # loop over all timesteps
    for t in range(len(angles[0][:n_max])):                   
        pressures = []
        # go through different angles 
        for z in angle_list:        
             # append for each angle the pressure of the current timestep
             pressures.append(np.array(angles[z])[t])    
                
        # norm colors for each image individually    viridis/RdBu      
        colors = matplotlib.cm.get_cmap('viridis')(pressures / max_pr ) 
        colorcycle = 'darkred'
    
        # do some statistics
        mean = np.round(np.nanmean(pressures))
        sd = np.round(np.nanstd(pressures))
        CoV = np.round(sd/mean, 2)
        res_angles['mean_pr_angles (Pa)'].append(mean)
        res_angles['sd_pr_angles (Pa)'].append(sd)
        res_angles['CoV'].append(CoV)
        

        # Mode that shows and norms up to 1000 Pa
        if small_pressure == False:
        
            # now use 1000 as maximum
            x = [np.cos(i*np.pi/180) for i in angle_list] * (pressures / np.array([1000]*len(pressures)) ) 
            y = [np.sin(i*np.pi/180) for i in angle_list] * (pressures / np.array([1000] *len(pressures)) ) 
            # combined figure
            # plot circles
            circle_100pa = plt.Circle((0, 0), 100/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_250pa = plt.Circle((0, 0), 250/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_500pa = plt.Circle((0, 0), 500/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_750pa = plt.Circle((0, 0), 750/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            ax1.text(0.5, 0.57, '100 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.text(0.5, 0.65, '250 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.text(0.5, 0.77, '500 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.text(0.5, 0.9, '750 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.add_artist(circle_100pa)
            ax1.add_artist(circle_250pa)
            ax1.add_artist(circle_500pa)
            ax1.add_artist(circle_750pa)
            ax1.axis('equal')  
            ax1.scatter(x,y, s=22, c=colors)
            ax1.set_xlim([-1, 1])
            ax1.set_ylim([-1, 1])
            ax1.axis('off')
            # annotate CoV    
            ax1.text(0.01, 0.91,'Coefficient of Variation: '+str(CoV), 
             horizontalalignment='center',
             verticalalignment='center',
             transform = ax1.transAxes, fontsize=9.2)  
            
            # annotate time if timestep is given
            if dt is not None:
                ax1.text(0.03, 0.98,str(timedelta(seconds=t*dt)), 
                  horizontalalignment='center',
                  verticalalignment='center',
                  transform = ax1.transAxes, fontsize=12)  

                
            # show quiver plot on the right side
            plot = plt.imread(plots[t])
            ax2.imshow(plot)
            plt.axis('off')
            ax2.axis('off')
            # save figure
            f.savefig(output+'//plot_{}.png'.format(str(t).zfill(4)), dpi=300)
            ax1.cla()
            ax2.cla()
            # Single figure
            # plot circles
            circle_100pa = plt.Circle((0, 0), 100/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_250pa = plt.Circle((0, 0), 250/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_500pa = plt.Circle((0, 0), 500/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_750pa = plt.Circle((0, 0), 750/ 1000 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            axb.text(0.5, 0.57, '100 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.text(0.5, 0.65, '250 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.text(0.5, 0.77, '500 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.text(0.5, 0.9, '750 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.add_artist(circle_100pa)
            axb.add_artist(circle_250pa)
            axb.add_artist(circle_500pa)
            axb.add_artist(circle_750pa)   
            axb.axis('equal')  
            axb.scatter(x,y, s=22, c=colors)
            axb.set_xlim([-1, 1])
            axb.set_ylim([-1, 1])
            axb.axis('off')
            plt.savefig(output+'//single_{}.png'.format(str(t).zfill(4)), dpi=300)
            axb.cla()
            
     # Mode that shows and norms up to 100 Pa
        if small_pressure == True:
            # now use 100 as maximum
            x = [np.cos(i*np.pi/180) for i in angle_list] * (pressures / np.array([100]*len(pressures)) ) 
            y = [np.sin(i*np.pi/180) for i in angle_list] * (pressures / np.array([100] *len(pressures)) ) 
            # combined figure
            # plot circles
            circle_a = plt.Circle((0, 0), 10/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_b = plt.Circle((0, 0), 25/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_c = plt.Circle((0, 0), 50/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            ax1.text(0.5, 0.57, '10 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.text(0.5, 0.65, '25 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.text(0.5, 0.77, '50 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes,fontsize=fontsize)
            ax1.add_artist(circle_a)
            ax1.add_artist(circle_b)
            ax1.add_artist(circle_c)
            ax1.axis('equal')  
            ax1.scatter(x,y, s=22, c=colors)
            ax1.set_xlim([-1, 1])
            ax1.set_ylim([-1, 1])
            ax1.axis('off')
            # annotate CoV    
            ax1.text(0.01, 0.91,'Coefficient of Variation: '+str(CoV), 
             horizontalalignment='center',
             verticalalignment='center',
             transform = ax1.transAxes, fontsize=9.2)  
            
            # annotate time if timestep is given
            if dt is not None:
                ax1.text(0.03, 0.98,str(timedelta(seconds=t*dt)), 
                  horizontalalignment='center',
                  verticalalignment='center',
                  transform = ax1.transAxes, fontsize=12)  
            # show quiver plot on the right side
            plot = plt.imread(plots[t])
            ax2.imshow(plot)
            plt.axis('off')
            ax2.axis('off')
            # save figure
            f.savefig(output+'//plot_{}.png'.format(str(t).zfill(4)), dpi=300)
            ax1.cla()
            ax2.cla()
            
            # single figure
            # plot circles
            circle_a = plt.Circle((0, 0), 10/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_b = plt.Circle((0, 0), 25/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            circle_c = plt.Circle((0, 0), 50/ 100 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            #circle_750pa = plt.Circle((0, 0), 100/ 300 , color=colorcycle, zorder=10, fill=False, linestyle='--')
            axb.text(0.5, 0.57, '10 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.text(0.5, 0.65, '25 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.text(0.5, 0.77, '50 Pa', color = colorcycle ,horizontalalignment='center', verticalalignment='center', transform=axb.transAxes,fontsize=fontsize)
            axb.add_artist(circle_a)
            axb.add_artist(circle_b)
            axb.add_artist(circle_c)
            axb.axis('equal')  
            axb.scatter(x,y, s=22, c=colors)
            axb.set_xlim([-1, 1])
            axb.set_ylim([-1, 1])
            axb.axis('off')
            plt.savefig(output+'//single_{}.png'.format(str(t).zfill(4)), dpi=300)
            axb.cla()

    # save excel file     
    ae = pd.DataFrame.from_dict(res_angles)
    ae.columns = ['mean_pr_angles (Pa)',
                  'sd_pr_angles (Pa)',
                  'CoV',]

    ae.to_excel(output+'/angles_eval.xlsx')

    return ae





