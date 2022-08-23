# -*- coding: utf-8 -*-

'''Gleeble data handler


'''

software_version = '1-0'

from collections import OrderedDict as orddict
import numpy as np
import math
import os
import sys
import openpyxl as opyx
import scipy.optimize as sciop
from numba import jit

import common_exceling_relax as cex

class Testseries:
    
    def __init__(self, num, T, SR, strain, t_hold):
        ''' '''
        
        vd = self.var_d = orddict()
        vd['num'] = num
        vd['nom_T'] = T
        vd['nom_SR'] = SR
        vd['nom_strain'] = strain
        vd['nom_t_hold'] = t_hold
        self.data_d = orddict()
        self.SRX_d = orddict()
        self.SRX_data_d = orddict()
        
        return

############### equations #####################

def pert_SRX_basic_eq(np_times, np_stresses, rec_stresses, gg_stresses):
    ''' '''
    
    SRXs = (np_stresses - rec_stresses) / (gg_stresses - rec_stresses)
    SRXs = np.nan_to_num(SRXs)
    SRXs = np.clip(SRXs, 0, 1)
    
    return SRXs


############### data fitting ###################

#- JMAK equation

def find_SRX_minmax(times, SRXs, min, max):
    ''' '''
    
    find_times, find_SRXs = [], []
    for i, SRX in enumerate(SRXs):
        min_chk = SRX > min
        max_chk = SRX < max
        if min_chk and max_chk:
            time = times[i]
            find_times.append(time)
            find_SRXs.append(SRX)
    
    find_times = np.array(find_times)
    find_SRXs = np.array(find_SRXs)
    
    return find_times, find_SRXs

def wrap_jmak_fitter(times, SRXs, fit_inits, fit_type_, t50_val_):
    ''' '''
    
    global fit_times, fit_SRXs, fit_counter, fit_type, t50_val
    
    fit_type = fit_type_
    t50_val = t50_val_
    if fit_type in ('full', 't50_lock'):
        fit_times = times
        fit_SRXs = SRXs
    elif fit_type == '20-80_SRX':
        min, max = 0.2, 0.8
        fit_times, fit_SRXs = find_SRX_minmax(times, SRXs, min, max)
    
    fit_counter = 0
    a00_init = fit_inits
    my_meth = 'Nelder-Mead'
    my_opts = {'maxiter':10000}
    my_bounds = []#[(None,None),(1.0,4.0)]
    if my_meth == 'Nelder-Mead':
        res = sciop.minimize(jmak_sum_of_diff, a00_init, method=my_meth, options=my_opts)
    else:
        res = sciop.minimize(jmak_sum_of_diff, a00_init, method=my_meth, options=my_opts, bounds=my_bounds)
    a1 = res['x']
    
    return a1

def jmak_sum_of_diff(fit_vars):
    ''' '''
    
    global fit_counter
    
    if fit_type in ('full', '20-80_SRX'):
        k, n = fit_vars
        jmak_arr = 1-np.exp(k*fit_times**n)
    elif fit_type == 't50_lock':
        n, = fit_vars
        jmak_arr = 1-np.exp(np.log(0.5)*(fit_times/t50_val)**n)
    diff_arr = fit_SRXs - jmak_arr
    diff_total = np.sum(np.absolute(diff_arr))
    
    #progress info
    fit_counter += 1
    printing = 'no'
    if printing == 'yes':
        if fit_counter % 100 == 0:
            print('count: %d' %fit_counter)
            print('diff_total: %.3f' %diff_total)
    
    return diff_total

#- Zurob equations

def Zurob_constants(T_degC, fit_vars, gg_vars, sig_start, sig_y, mat_type):
    ''' '''
    
    vals_d = orddict()
    #-material constants
    vals_d['M_T'] = 3.1 #taylor factor
    vals_d['alpha_r'] = 0.15 #constant
    vals_d['angstrom_val'] = angstrom_val = 1.0E-10 #m, angstrom constant value
    vals_d['b'] = 2.5*angstrom_val #length of burger's vector
    vals_d['delta'] = 0.5E-9 #m, grain boundary width
    vals_d['D_gb0'] = D_gb0 = 6.35E-15 #self diffusion constant for iron grain boundary
    vals_d['Q_FE'] = Q_FE = 55.7E3 #J/mol, Activation energy of self diffusion
    vals_d['R_g'] = R_g = 8.3145 #J/mol, gas constant
    vals_d['k_B'] = 1.3807E-23 #Boltzmann constant
    vals_d['N'] = N = 4 #number of atoms per unit cell
    #-material composition
    comp_d = make_comp_d(mat_type)
    wtC = comp_d['wtC']
    #-gg curve variables
    vals_d['sig_y'] = sig_y #Pa, yield stress of fully recrystallized material
    vals_d['a2'] = gg_vars[0] #fitting parameter for sig_gg
    vals_d['b2'] = gg_vars[1] #fitting parameter for sig_gg
    #-temperature-dependent variables
    vals_d['T_degC'] = T_degC #= 1050.0
    vals_d['T_degK'] = T_degK = T_degC + 273.15
    E_20C = 210e9 # Pa
    E = vals_d['E'] = elastic_modulus(E_20C, T_degC) #6.8654e9 #Pa, from matlab script
    vals_d['mu'] = mu = 3*E/8 #shear modulus
    vals_d['deltaD_gb'] = 6.35E-15*np.exp(-(55.7E3)/(8.3145*T_degK)) #2.17E-17 #combination value, figure out where this is from
    vals_d['D_gb'] = D_gb0*np.exp(-Q_FE/(R_g*T_degK))
    vals_d['rho_gamma'] = rho_gamma = austenite_density(comp_d, T_degC) #8099.79 - 0.506*T_degC
    vals_d['V_mFE'] = 55.845E-3 / rho_gamma
    #-debye frequency
    vals_d['a_0'] = a_0 = (8.1593E-6*T_degK + 0.35519 + 1.7341E-3*wtC)*1.0E-9
    vals_d['v'] = v = np.sqrt(E/rho_gamma)
    vals_d['V'] = V = a_0**3
    vals_d['v_d'] = v_d = np.cbrt(6*np.pi*N/V)*v#1.1081e13 #
    #-fitting parameters
    vals_d['U_a'] = fit_vars[0]  #J/mol
    vals_d['V_a'] = fit_vars[1]  #m**3
    vals_d['Q_d'] = fit_vars[2]  #J/mol
    vals_d['k'] = k = fit_vars[3] 
    vals_d['Sv'] = Sv = 80839.75
    vals_d['k_Sv'] = k_Sv = k*Sv #1/m
    #-starting stress
    vals_d['sig_start'] = sig_start
    
    return vals_d

def make_comp_d(mat_type):
    ''' '''
    
    comp_d = orddict()
    if mat_type == 'Raex400-old':
        comp_d['wtC'] = 0.142;
        comp_d['wtSi'] = 0.21
        comp_d['wtMn'] = 1.1
        comp_d['wtAl'] = 0.026
        comp_d['wtCr'] = 0.705
        comp_d['wtMo'] = 0.191
        comp_d['wtTi'] = 0.025
        comp_d['wtB'] = 0.0019
        comp_d['wtN'] = 0.0053
        comp_d['wtNb'] = 0.002
        comp_d['wtNi'] = 0.054
        comp_d['wtV'] = 0.008
        comp_d['wtCu'] = 0.041
        comp_d['wtCo'] = 0.015
    elif mat_type == '1523':
        # 0.16C – 0.2Si – 1.0Mn – 0.5Cr – 0.5Ni – 0.03Al – 0.0015B – 0.005N
        comp_d['wtC'] = 0.16
        comp_d['wtSi'] = 0.2
        comp_d['wtMn'] = 1.0
        comp_d['wtAl'] = 0.03
        comp_d['wtCr'] = 0.5
        comp_d['wtMo'] = 0.0
        comp_d['wtTi'] = 0.0
        comp_d['wtB'] = 0.0015
        comp_d['wtN'] = 0.005
        comp_d['wtNb'] = 0.0
        comp_d['wtNi'] = 0.5
        comp_d['wtV'] = 0.0
        comp_d['wtCu'] = 0.0
        comp_d['wtCo'] = 0.0
    elif mat_type == '1524':
        # 0.16C – 0.2Si–1.1Mn – 0.5Cr – 0.5Ni – 0.25Mo – 0.03Al – 0.0015B – 0.0043N
        comp_d['wtC'] = 0.16
        comp_d['wtSi'] = 0.2
        comp_d['wtMn'] = 1.1
        comp_d['wtAl'] = 0.03
        comp_d['wtCr'] = 0.5
        comp_d['wtMo'] = 0.25
        comp_d['wtTi'] = 0.0
        comp_d['wtB'] = 0.0015
        comp_d['wtN'] = 0.0043
        comp_d['wtNb'] = 0.0
        comp_d['wtNi'] = 0.5
        comp_d['wtV'] = 0.0
        comp_d['wtCu'] = 0.0
        comp_d['wtCo'] = 0.0
    elif mat_type == '1525':
        # 0.16C – 0.2Si–1.1Mn – 0.5Cr – 0.5Ni – 0.25Mo – 0.04Nb– 0.03Al – 0.0015B – 0.0050.041N
        comp_d['wtC'] = 0.16
        comp_d['wtSi'] = 0.2
        comp_d['wtMn'] = 1.1
        comp_d['wtAl'] = 0.03
        comp_d['wtCr'] = 0.5
        comp_d['wtMo'] = 0.25
        comp_d['wtTi'] = 0.0
        comp_d['wtB'] = 0.0015
        comp_d['wtN'] = 0.005
        comp_d['wtNb'] = 0.04
        comp_d['wtNi'] = 0.5
        comp_d['wtV'] = 0.0
        comp_d['wtCu'] = 0.0
        comp_d['wtCo'] = 0.0
    
    return comp_d

@jit(nopython=True)
def Zurob_SRX_basic_eq_np(times, gg_stresses, sig_start, deltaD_gb, V_mFE, b, R_g, T_degK, Q_d, sig_y, M_T, alpha_r, mu, v_d, E, U_a, V_a, k_B, k_Sv):
    '''Run Zurob SRX equation. Use numba.jit for enhanced performance.'''
    
    #main loop with constant temperature
    arr_len = len(times)
    sig_rels = np.zeros(arr_len)
    sig_rels[0] = sig_start
    sig_recs = np.zeros(arr_len)
    sig_recs[0] = sig_start
    sig_ggs = gg_stresses
    X_rexs = np.zeros(arr_len)
    I = 0.0
    #-grain boundary mobility
    M_pure = deltaD_gb*V_mFE / (10*b**2*R_g*T_degK)
    M_gb_now = M_pure*np.exp(-Q_d/(R_g*T_degK))
    M_gb_prev = M_gb_now
    #starting values
    sig_rec = sig_recs[0]
    rho = (sig_rec-sig_y)**2 / (M_T*alpha_r*mu*b)**2
    G_prev = rho*mu*b**2/2
    G_t0 = G_prev
    #-number of recrystallization sites
    gamma_gb = 1.3115 - 0.0005*T_degK
    A_c = 4*np.pi*(2*gamma_gb/G_t0)**2
    N_rex = k_Sv/A_c
    
    for ii, t_now in enumerate(times[1:]):
        i = ii+1
        t_prev = times[ii]
        delta_t = t_now - t_prev
        #driving force for recrystallization
        rho = (sig_rec-sig_y)**2 / (M_T*alpha_r*mu*b)**2
        G_now = rho*mu*b**2/2
        #integration part
        MG_now = M_gb_now * G_now
        MG_prev = M_gb_prev * G_prev
        MG_avg = (MG_now + MG_prev) / 2.0
        I += MG_avg*delta_t
        G_prev = G_now
        #recrystallized fraction and stresses
        X_rex = 1 - np.exp(-N_rex*I**3)
        X_rexs[i] = X_rex
        sig_gg = sig_ggs[i]
        sig_rel = (1-X_rex)*sig_rec + X_rex*sig_gg
        sig_rels[i] = sig_rel
        #-
        if sig_rel > sig_y:
            dsr_per_dt1 = -64*(sig_rel-sig_y)**2*v_d / (9*M_T**3*alpha_r**2*E)
            dsr_per_dt2 = np.exp(-U_a / (R_g*T_degK))
            dsr_per_dt3 = np.sinh((sig_rel-sig_y)*V_a / (k_B*T_degK))
            dsig_rec_per_dt = dsr_per_dt1*dsr_per_dt2*dsr_per_dt3
        else:
            dsig_rec_per_dt = 0
        sig_rec += dsig_rec_per_dt*delta_t
        sig_recs[i] = sig_rec
    
    return sig_recs, sig_rels, sig_ggs, X_rexs

def Zurob_SRX_basic_eq(vals_d, times): #old and slow version, don't use this
    ''' '''
    
    #-values for equations
    comp_d = vals_d['mat_comp']
    
    #main loop with constant temperature
    sig_rels = [vals_d['sig_start']]
    sig_recs = [vals_d['sig_start']]
    sig_ggs = [f_sig_gg(vals_d, times[0])]
    X_rexs = [0.0]
    Is = [0.0]
    rhos = []
    Gs = []
    #-grain boundary mobility
    vals_d['M_pure'] = M_pure = f_M_pure(vals_d)
    M_gb_now = f_M_gb(vals_d)
    M_gb_prev = M_gb_now
    #starting values
    sig_rel = sig_rels[0]
    sig_rec = sig_recs[0]
    vals_d['X_rex'] = X_rexs[0]
    vals_d['rho'] = rho = f_rho(vals_d, sig_rec)
    vals_d['G_prev'] = G_prev = f_G(vals_d, rho)
    G_t0 = G_prev
    Gs.append(G_prev)
    #-number of recrystallization sites
    N_rex = f_N_rex(vals_d, G_t0)
    
    
    for i, t_now in enumerate(times[1:]):
        t_prev = times[i]
        delta_t = t_now - t_prev
        #add vals at start of new timestep
        sig_rec = sig_recs[i]
        #driving force for recrystallization
        rho = f_rho(vals_d, sig_rec)
        rhos.append(rho)
        G_now = f_G(vals_d, rho)
        Gs.append(G_now)
        #integration part
        MG_now = M_gb_now * G_now
        MG_prev = M_gb_prev * G_prev
        MG_avg = (MG_now + MG_prev) / 2.0
        I = Is[i] + MG_avg*delta_t
        Is.append(I)
        G_prev = G_now
        #recrystallized fraction and stresses
        X_rex = f_X_rex(N_rex, I)
        X_rexs.append(X_rex)
        sig_gg = f_sig_gg(vals_d, t_now)
        sig_ggs.append(sig_gg)
        sig_rel = f_sig_rel(X_rex, sig_rec, sig_gg)
        sig_rels.append(sig_rel)
        #-
        dsig_rec_per_dt = f_dsig_rec_per_dt(vals_d, sig_rel)
        sig_rec = sig_recs[i] + dsig_rec_per_dt*delta_t
        sig_recs.append(sig_rec)
    
    return sig_recs, sig_rels, sig_ggs, X_rexs

def f_M_pure(d1):
    ''' '''
    
    M_pure = d1['deltaD_gb']*d1['V_mFE'] / (10*d1['b']**2*d1['R_g']*d1['T_degK'])
    
    return M_pure

def f_M_gb(d1):
    ''' '''
    
    M_gb = d1['M_pure']*np.exp(-d1['Q_d']/(d1['R_g']*d1['T_degK']))
    
    return M_gb

def f_rho(d1, sig_rec):
    ''' '''
    
    rho = (sig_rec-d1['sig_y'])**2 / (d1['M_T']*d1['alpha_r']*d1['mu']*d1['b'])**2
    
    return rho

def f_G(d1, rho):
    ''' '''
    
    G = rho*d1['mu']*d1['b']**2/2
    
    return G

def f_N_rex(d1, G_t0):
    ''' '''
    
    d1['gamma_gb'] = gamma_gb = 1.3115 - 0.0005*d1['T_degK']
    d1['A_c'] = A_c = 4*np.pi*(2*gamma_gb/G_t0)**2
    d1['N_rex'] = N_rex = d1['k_Sv']/A_c
    
    return N_rex

def f_X_rex(N_rex, I):
    ''' '''
    
    X_rex =  1 - np.exp(-N_rex*I**3)
    
    return X_rex

def f_sig_gg(d1, t):
    ''' '''

    sig_gg = d1['a2'] - d1['b2']*np.log10(t)
    
    return sig_gg

def f_sig_rel(X_rex, sig_rec, sig_gg):
    ''' '''
    
    sig_rel = (1-X_rex)*sig_rec + X_rex*sig_gg
    
    return sig_rel

def f_dsig_rec_per_dt(d1, sig_rel):
    ''' '''
    
    if sig_rel > d1['sig_y']:
        dsr_per_dt1 = -64*(sig_rel-d1['sig_y'])**2*d1['v_d'] / (9*d1['M_T']**3*d1['alpha_r']**2*d1['E'])
        dsr_per_dt2 = np.exp(-d1['U_a'] / (d1['R_g']*d1['T_degK']))
        dsr_per_dt3 = np.sinh((sig_rel-d1['sig_y'])*d1['V_a'] / (d1['k_B']*d1['T_degK']))
        dsig_rec_per_dt = dsr_per_dt1*dsr_per_dt2*dsr_per_dt3
    else:
        dsig_rec_per_dt = 0
    
    return dsig_rec_per_dt

def austenite_density(comp_d, T_degC):
    ''' '''
    
    density = 8099.79-0.5060*T_degC + (-118.26+0.00739*T_degC)*comp_d['wtC'] + (-7.59+3.422E-3*T_degC-5.388E-7*T_degC**2.0-0.014271*comp_d['wtCr'])*comp_d['wtCr'] + (1.54+2.267E-3*T_degC-11.26E-7*T_degC**2+0.062642*comp_d['wtNi'])*comp_d['wtNi'] - 68.24*comp_d['wtSi'] - 6.01*comp_d['wtMn'] + 12.45*comp_d['wtMo']
    
    return density

def elastic_modulus(E_20C, T_degC):
    ''' '''
    
    mode = 'FEM-malli' #FEM-malli | matlab-skriptu
    
    if mode == 'matlab-skriptu':
        Ts=[19.5845697329, 94.3620178042, 202.96735905, 315.133531157, 398.81305638, 425.519287834, 537.685459941, 648.071216617, 760.237388724, 870.623145401, 981.008902077, 1091.39465875, 1201.78041543]
        facs=[1, 1, 0.901098901099, 0.78021978022, 0.701098901099, 0.67032967033, 0.49010989011, 0.21978021978, 0.112087912088, 0.0703296703297, 0.0505494505495, 0.021978021978, 0.0021978021978]
    elif mode == 'FEM-malli':
        Ts = [20., 100., 200., 300., 400., 500., 600., 700., 800., 900., 1000., 1100., 1200., 1300., 1350.]
        facs = [1., 0.96952381, 0.93095238, 0.89285714, 0.85428571, 0.81619048, 0.7052381 , 0.49142857, 0.32952381, 0.20190476, 0.11238095, 0.09047619, 0.07142857, 0.05714286, 0.05238095]
    
    for i, T in enumerate(Ts):
        T_chk = T >= T_degC
        if T_chk:
            T1 = Ts[i-1]
            T2 = T
            f1 = facs[i-1]
            f2 = facs[i]
            break
    
    fac = lin_interpol(T1, T2, T_degC, f1, f2)
    E = E_20C * fac
    
    return E

def lin_interpol(x1, x2, x_get, y1, y2):
    ''' '''
    
    y_get = ((y2-y1)/(x2-x1))*(x_get-x1) + y1
    
    return y_get

def Zurob_sum_of_diff(fit_vars):
    ''' '''
    
    global fit_counter
    
    locs_Z_fake = ''
    vals_d, sig_recs, sig_rels, sig_ggs, SRXs = wrap_Zurob_runner(times_fit, gg_stresses_fit, locs_Z_fake, fit_vars, gg_vars_fit, sig_start_fit, T_degC_fit, sig_y_fit, mat_type)
    Zurob_arr = np.array(sig_rels)
    diff_arr = stresses_fit - Zurob_arr
    diff_total = np.sum(np.absolute(diff_arr))
    
    #progress info
    fit_counter += 1
    printing = 'yes'
    if printing == 'yes':
        if fit_counter % 100 == 0:
            print('count: %d' %fit_counter)
            print('diff_total: %.3f' %diff_total)  
            
    return diff_total

def wrap_Zurob_fitter(T_degC, fit_vars0, gg_vars, sig_start, sig_y, times, stresses, gg_stresses, mat_type_):
    ''' '''
    
    global fit_counter, times_fit, stresses_fit, gg_vars_fit, sig_start_fit, T_degC_fit, sig_y_fit, gg_stresses_fit, mat_type
    
    times_fit = np.array(times)
    stresses_fit = np.array(stresses)
    gg_stresses_fit = gg_stresses
    gg_vars_fit = gg_vars
    sig_start_fit = sig_start
    T_degC_fit = T_degC
    sig_y_fit = sig_y
    mat_type = mat_type_
    
    fit_counter = 0
    my_meth = 'Nelder-Mead' #'Nelder-Mead'
    my_opts = {'maxiter':10000}
    my_bounds = [[None,None],[None,None],[None,None],[5e-5,5e-2]]
    if my_meth == 'Nelder-Mead':
        res = sciop.minimize(Zurob_sum_of_diff, fit_vars0, method=my_meth, options=my_opts)
    elif my_meth == 'TNC':
        res = sciop.minimize(Zurob_sum_of_diff, fit_vars0, method=my_meth, options=my_opts, bounds=my_bounds)
    fit_vars = res['x']    
    
    return fit_vars

def wrap_Zurob_runner(np_times, sig_ggs, locs_Z, fit_vars, gg_vars, sig_start, T_degC, sig_y, mat_type):
    ''' '''
    
    vals_d = Zurob_constants(T_degC, fit_vars, gg_vars, sig_start, sig_y, mat_type)
    sig_start, deltaD_gb, V_mFE, b, R_g, T_degK, Q_d, sig_y, M_T, alpha_r, mu, v_d, E, U_a, V_a, k_B, k_Sv = vals_d['sig_start'], vals_d['deltaD_gb'], vals_d['V_mFE'], vals_d['b'], vals_d['R_g'], vals_d['T_degK'], vals_d['Q_d'], vals_d['sig_y'], vals_d['M_T'], vals_d['alpha_r'], vals_d['mu'], vals_d['v_d'], vals_d['E'], vals_d['U_a'], vals_d['V_a'], vals_d['k_B'], vals_d['k_Sv']
    # sig_recs, sig_rels, sig_ggs, SRXs = Zurob_SRX_basic_eq(vals_d, np_times)
    sig_recs, sig_rels, sig_ggs, SRXs = Zurob_SRX_basic_eq_np(np_times, sig_ggs, sig_start, deltaD_gb, V_mFE, b, R_g, T_degK, Q_d, sig_y, M_T, alpha_r, mu, v_d, E, U_a, V_a, k_B, k_Sv)
    if locs_Z != '':
        [sig_recs, sig_rels, sig_ggs, SRXs] = Z_data_back_to_normal(locs_Z, [sig_recs, sig_rels, sig_ggs, SRXs])
    
    return vals_d, sig_recs, sig_rels, sig_ggs, SRXs

def Z_data_back_to_normal(locs_Z, lists):
    ''' '''
    
    short_lists = []
    for i in locs_Z:
        for j, l1 in enumerate(lists):
            val = l1[i]
            try:
                short_lists[j].append(val)
            except IndexError:
                short_lists.append([val])
    
    return short_lists

#################### data handeling ######################

def wrap_tab_data(file_pth, fileformat, pavg_range, ang_data_chk='no', opp_val_chk='yes'):
    ''' '''
    
    #read data into dict
    if fileformat in ('dat', 'csv'):
        values_d = cex.read_csv(file_pth)
        F_sum = sum(values_d['Force(kN)'])
        if (F_sum < 0) and (opp_val_chk == 'yes'):
            # opp_heads = ['Force(kN)', 'Jaw(mm)', 'Strain', 'Stress(MPa)']
            opp_heads = ['Strain', 'Stress(MPa)']
            wb_d_opposite_numbers(values_d, opp_heads)
    elif fileformat == 'xlsx':
        high_speed = 'no'
        if high_speed == 'no':
            values_d = cex.tab_data_from_excel(file_pth, ang_data_chk)
        elif high_speed == 'yes':
            values_d = cex.tab_data_from_excel_read_only(file_pth)
    #
    #run point averaging
    values_pavg_d = wrap_point_averaging_relax(values_d, pavg_range)
    #add strain rates
    calc_SR(values_d)
    calc_SR(values_pavg_d)
    #get angle and norm data for strain|stress
    wrap_ang_norm_data(values_d, ang_data_chk)
    wrap_ang_norm_data(values_pavg_d, ang_data_chk)

    
    return values_d, values_pavg_d

def data_thinning_r_start(d1, relax_start, thin_skip):
    '''' '''
    
    for lbl, vals in d1.items():
        new_vals = []
        for i, val in enumerate(vals):
            chk1 = i % thin_skip == 0
            chk2 = i < relax_start[0]+100
            if chk1 or chk2:
                new_vals.append(val)
        d1[lbl] = new_vals
    
    return

def data_thinning_s_freq(d1, thin_skip):
    ''' '''
    
    #get sampling frequency
    t_diffs, s_freqs = get_s_freq(d1)
    #thin inter-hit data
    press_s_freq = s_freqs[1]
    for lbl, vals in d1.items():
        new_vals = []
        for i, val in enumerate(vals):
            s_freq = s_freqs[i]
            chk1 = i % thin_skip == 0
            chk2 = s_freq == press_s_freq
            if chk1 or chk2:
                new_vals.append(val)
        d1[lbl] = new_vals
    
    return

def get_s_freq(d1):
    ''' '''
    
    t_diffs = ['']
    s_freqs = ['']
    times = d1['Time(sec)']
    prev_time = times[0]
    for time in times[1:]:
        t_diff = time - prev_time
        t_diffs.append(t_diff)
        try:
            s_freqs.append(round(1/t_diff))
        except ZeroDivisionError:
            s_freqs.append('')
        prev_time = time
    
    
    return t_diffs, s_freqs

def wrap_ang_norm_data(vals_d, ang_data_chk):
    ''' '''
    
    # ang_s_lim = ...
    # ang_e_lim = ...
    i_jump_fwd = 15
    i_jump_bck = i_jump_fwd*-1
    # s_val = vals_d['Strain'][0]
    # e_val = vals_d['Strain'][-1]
    ang_base = 'Stress(MPa)' #Strain|Stress(MPa)
    x_data, y_data = vals_d['Time(sec)'], vals_d[ang_base]
    norm_y_data = normalize_data(y_data, max(y_data))
    vals_d['norm_stress'] = norm_y_data
    if ang_data_chk == 'yes':
        ang_s_data = get_ang_data(x_data, norm_y_data, i_jump_fwd)
        ang_e_data = get_ang_data(x_data, norm_y_data, i_jump_bck)
        vals_d['ang_s'] = ang_s_data
        vals_d['ang_e'] = ang_e_data
    
    return

def normalize_data(data, normalizer):
    ''' '''
    
    norm_data = []
    # min_val = min(data)
    # max_val = max(data)
    for val in data:
        # norm_val = (val - min_val) / (max_val - min_val)
        norm_val = val / normalizer
        norm_data.append(norm_val)
    
    
    return norm_data

def get_ang_data(x_data, y_data, i_jump):
    ''' '''
    
    ang_data = []
    
    if i_jump > 0:
        y_val = y_data[0]
    else:
        y_val = y_data[-1]
        
    for i, my_x in enumerate(x_data):
        new_i = i+i_jump
        try:
            if new_i < 0:
                raise IndexError
            jump_y = y_data[new_i]
            jump_x = x_data[new_i]
        except IndexError:
            ang_data.append('')
            continue
        my_k = (jump_y - y_val) / (jump_x - my_x)
        my_ang = math.atan(my_k) * 180 / math.pi
        ang_data.append(my_ang)
    
    return ang_data

def calc_SR(my_d):
    ''' '''
    
    times, strains = my_d['Time(sec)'][1:], my_d['Strain'][1:]
    SRs = [0.0]
    for i, time_now in enumerate(times):
        prev_time = times[i-1]
        prev_strain = strains[i-1]
        strain_now = strains[i]
        try:
            SR = (strain_now - prev_strain) / (time_now - prev_time)
        except ZeroDivisionError: #fixes a bug that gleeble sometimes does when changing sampling frequency
            continue
        SRs.append(SR)
    my_d['Strain rate(1/s)'] = SRs    
    
    return

def wb_d_opposite_numbers(d1, opp_heads):
    ''' '''
    
    for head, vals in d1.items():
        if head in opp_heads:
            # opp_vals = []
            # for val in vals:
                # opp_vals.append(val*-1)
            opp_vals = list(map(lambda x:x*-1, vals))
            d1[head] = opp_vals
    
    return

def wrap_point_averaging_relax(my_d, avg_range):
    ''' '''
    
    avg_val = max(1, avg_range // 2)
    
    my_pavg_d = orddict()
    for key, vals in my_d.items():
        if key == 'Time(sec)':
            my_pavg_d['Time(sec)'] = my_d['Time(sec)'][avg_val:-avg_val]
        else:
            avg_vals = point_averaging(vals, avg_val)
            my_pavg_d[key] = avg_vals
    
    return my_pavg_d

def point_averaging(vals, avg_val):
    ''' '''
    
    avg_vals = []
    for i in range(avg_val, len(vals)-avg_val):
        cut_list = vals[i-avg_val:i+avg_val+1]
        cut_avg = sum(cut_list) / len(cut_list)
        avg_vals.append(cut_avg)
    
    return avg_vals

def find_compress_relax_start_points(vpd, nom_strain, nom_SR):
    ''' '''
    
    times, strains, SRs = vpd['Time(sec)'], vpd['Strain'], vpd['Strain rate(1/s)']
    compress_start = ''
    relax_chk2_init = 0
    for i, val in enumerate(strains):
        SR = SRs[i]
        time = times[i]
        compress_chk = val > 0.0015 and compress_start == ''
        if compress_chk:
            compress_start = (i, time)
        relax_chk1 = val >= nom_strain
        relax_chk2 = relax_chk2_init == 1 and SR < 0.8*nom_SR
        if relax_chk1 or relax_chk2:
            relax_start = (i, time)
            break
        if SR > 0.9*nom_SR:
            relax_chk2_init = 1
    
    
    return compress_start, relax_start

def find_cr_start_points_new(vpd, find_type, c_lim, c_forced_time, r_lim):
    ''' '''
    
    times, vals = vpd['Time(sec)'], vpd[find_type]
    if find_type == 'ang_s':
        max_ang = -123456789.0
        for ang in vals:
            try:
                if ang > max_ang:
                    max_ang = ang
            except TypeError:
                continue
        r_lim = max_ang*.99
    elif 'norm' in find_type:
        # r_lim = 0.99
        compress_start = (0, times[0])
    c_flag = 0
    for i, val in enumerate(vals):
        time = times[i]
        if c_forced_time == -1:
            c_chk = val > c_lim and c_flag == 0
        else:
            c_chk = time >= c_forced_time and c_flag == 0
        if c_chk:
            compress_start = (i, time)
            c_flag = 1
        r_chk = val > r_lim
        if r_chk:
            relax_start = (i, time)
            break
    
    return compress_start, relax_start

def relax_tsd_starter(temps, strains, hold_times, SRs, temp_str):
    '''Initiates a relaxation test series dict.
        Returns the initiated dict.'''
	
    test_series_dict = ts_dict = orddict()
    
    lt_check = temp_str == 'lt'
    if lt_check: 
        hold_times_dict = hold_times
	
    num = 1
    for T in temps:
        for SR in SRs:
            for strain in strains:
                if lt_check: hold_times = hold_times_dict[T]
                for t_hold in hold_times:
                    ts_dict[num] = Testseries(num, T, SR, strain, t_hold)
                    # this_dict['nom_T'] = this_temp
                    # this_dict['nom_SR'] = this_SR
                    # this_dict['nom_strain'] = this_strain
                    # this_dict['t_hold'] = this_t_hold
                    num += 1
	
    return ts_dict

def dhit_tsd_starter(T, strain, hold_times, SR):
    ''' '''
    
    test_series_dict = tsd = orddict()
    
    num = 1
    for t_hold in hold_times:
        tsd[num] = Testseries(num, T, SR, strain, t_hold)
        num += 1
    
    return tsd

def time_zeroer(times, start_loc):
    ''' '''
    
    times_zeroed = [0.0000001] #real zero causes mathematical errors, little offset here saves from a lot of errors
    for time in times[start_loc+1:]:
        time_zeroed = time - times[start_loc]
        times_zeroed.append(time_zeroed)
    
    return times_zeroed

def cut_values_pavg_d(values_pavg_d, compress_start, relax_start):
    ''' '''
    
    values_compress_d, values_relax_d = orddict(), orddict()
    for key, vals in values_pavg_d.items():
        if key == 'Time(sec)':
            times_C = time_zeroer(vals, compress_start[0])
            times_R = time_zeroer(vals, relax_start[0])
            values_compress_d[key] = times_C
            values_relax_d[key] = times_R
        else:
            values_compress_d[key] = vals[compress_start[0]:]
            values_relax_d[key] = vals[relax_start[0]:]
    
    return values_compress_d, values_relax_d

def zerostrain_cutter(datas):
    ''' '''
    
    datas_zerocut = orddict()
    #find zerostrain loc
    for i, strain in enumerate(datas['Strain']):
        zero_chk = strain >= 0.0
        if zero_chk:
            zs_loc = i
            break
    #cut datas to size
    for key, vals in datas.items():
        vals_zs = vals[zs_loc:]
        datas_zerocut[key] = vals_zs
    
    return datas_zerocut

############ creating test series objects ###############

def wrap_simple_tsder(load_dir_pth, pavg_range, thin_skip, opp_val_chk):
    ''' '''
    
    tsd = orddict()
    #os.walk syntax: [[dir_path],[sub_folders],[files]]
    pth_gen = list(os.walk(load_dir_pth))
    file_list = pth_gen[0][2]
    for file in file_list:
        print(file)
        if file == 'ts_params.txt':
            print('skipping...')
            continue
        file_name = file[:file.rfind('.')]
        fileformat = file[file.rfind('.')+1:]
        d1 = tsd[file_name] = orddict()
        filepth = load_dir_pth + file
        datas_d, datas_pavg_d = wrap_tab_data(filepth, fileformat, pavg_range, opp_val_chk=opp_val_chk)
        # thin_skip = 10
        data_thinning_s_freq(datas_pavg_d, thin_skip)
        d1['datas'] = datas_d
        d1['datas_pavg'] = datas_pavg_d
    
    return tsd

def wrap_relax_test_series_dicter(load_dir_path, temps, strains, hold_times, SRs, thin_skip, pavg_range, c_lim, c_forced_time, r_lim, temp_str='', printing=False):
    '''Creates a test series dict for relaxation data with time-strain tabular data, temp, strain, SR and hold time for each test.
        Returns this dict.'''
	
    test_series_dict = ts_dict = relax_tsd_starter(temps, strains, hold_times, SRs, temp_str)
    
    #os.walk syntax: [[dir_path],[sub_folders],[files]]
    path_generator = os.walk(load_dir_path)
    for this_gen in path_generator:
        xlsx_list = this_gen[2]
    
    # if test_mode == 'single_wb':
        # xlsx_list = [xlsx_list[0]]
    if printing == True: print('Reading files:')
    for this_xlsx in xlsx_list:
        skip_chk1 = '~$' in this_xlsx #prevent some random temporary files in mac
        skip_chk2 = '.' == this_xlsx[0] #prevent hidden files in mac
        skip_chk3 = 'ts_params.txt' == this_xlsx
        if skip_chk1 or skip_chk2 or skip_chk3:
            continue
        if printing == True: print(this_xlsx)
        #path name handling
        file_name = this_xlsx[:this_xlsx.rfind('.')]
        fileformat = this_xlsx[this_xlsx.rfind('.')+1:]
        file_pth = load_dir_path + this_xlsx
        #load data - .dat and .xlsx supported
        values_d, values_pavg_d = wrap_tab_data(file_pth, fileformat, pavg_range)
        #save to test series dict
        try:
            ts_name = int(file_name)
        except ValueError:
            ts_name = int(file_name.split('-')[0])
        ts = ts_sub_d = ts_dict[ts_name]
        nom_strain = ts.var_d['nom_strain']
        nom_SR = ts.var_d['nom_SR']
        cr_start_finder = 'norm' #old|ang|norm
        if cr_start_finder == 'old':
            compress_start, relax_start = find_compress_relax_start_points(values_pavg_d, nom_strain, nom_SR)
        elif cr_start_finder == 'norm':
            for key in values_pavg_d.keys():
                if 'norm' in key:
                    find_type = key
                    break
            compress_start, relax_start = find_cr_start_points_new(values_pavg_d, find_type, c_lim, c_forced_time, r_lim)
        #
        ts.var_d['c_start'] = compress_start
        ts.var_d['r_start'] = relax_start
        # data_thinning_r_start(values_pavg_d, relax_start, thin_skip)
        data_thinning_s_freq(values_pavg_d, thin_skip)
        values_compress_d, values_relax_d = cut_values_pavg_d(values_pavg_d, compress_start, relax_start)
        ts.var_d['c_stress'] = values_compress_d['Stress(MPa)'][0]
        ts.var_d['r_stress'] = values_relax_d['Stress(MPa)'][0]
        ts.var_d['r_strain'] = r_strain = values_relax_d['Strain'][0]
        ts.var_d['strain_diff'] = nom_strain - r_strain
        ts.var_d['T_min'] = T_min = min(values_pavg_d['TC1(C)'])
        ts.var_d['T_max'] = T_max = max(values_pavg_d['TC1(C)'])
        ts.var_d['T_diff'] = T_max - T_min
        #saves chosen data to test_series_dict
        ts.data_d['datas'] = values_d
        ts.data_d['datas_pavg'] = values_pavg_d
        ts.data_d['datas_compress'] = values_compress_d
        ts.data_d['datas_relax'] = values_relax_d

    if printing == True: print('Reading finished.')
    
    return ts_dict

def wrap_doublehit_tsder(load_dir_pth, temp, strain, hold_times, SR, pavg_range, thin_skip):
    ''' '''
    
    test_series_dict = tsd = dhit_tsd_starter(temp, strain, hold_times, SR)
    
    #os.walk syntax: [[dir_path],[sub_folders],[files]]
    pth_gen = list(os.walk(load_dir_pth))
    file_list = pth_gen[0][2]
    for file in file_list:
        print('%s,' %file, end='')
        # print(file)
        file_name = file[:file.rfind('.')]
        fileformat = file[file.rfind('.')+1:]
        filepth = load_dir_pth + file
        datas_d, datas_pavg_d = wrap_tab_data(filepth, fileformat, pavg_range)
        #save to test series dict
        file_name = file_name.replace('Nro','')
        file_name = file_name.replace('Nr','')
        try:
            ts_name = int(file_name)
        except ValueError:
            try:
                ts_name = int(file_name.split('-')[0])
            except ValueError:
                ts_name = int(file_name.split(' ')[0])
        ts_obj = tsd[ts_name]
        data_thinning_s_freq(datas_pavg_d, thin_skip)
        ts_obj.data_d['datas_orig'] = datas_d
        ts_obj.data_d['datas_pavg'] = datas_pavg_d
    
    print('Test series dicting completed!')
    
    return tsd


if __name__ == '__main__':
    
    
    
    pass