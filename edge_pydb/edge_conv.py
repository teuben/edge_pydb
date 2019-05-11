import numpy as np
from astropy.io import fits
from astropy.table import Table, Column, join
from astropy import units as u
from astropy.coordinates import SkyCoord
from uncertainties import ufloat
import uncertainties.unumpy as unp 


# Calculate galactocentric polar coordinates 
# (radius in arcsec, azangle in degrees from receding majaxis)
# Inputs should all be in degrees
def gc_polr(ra, dec, ra_gc, dec_gc, pa, inc):
    ctr = SkyCoord(ra_gc, dec_gc, unit="deg")
    pos = SkyCoord(ra, dec, unit="deg")
    # Polar vector in sky plane
    t_sky = ctr.position_angle(pos).degree
    r_sky = ctr.separation(pos).arcsecond
    #print(t_sky,r_sky)
    # Convert to galaxy plane
    x_sky = r_sky * np.cos(np.radians(t_sky - pa))
    y_sky = r_sky * np.sin(np.radians(t_sky - pa))
    x_gal = x_sky
    y_gal = y_sky/np.cos(np.radians(inc))
    # Reject very high inclinations (cannot be deprojected)
    y_gal[inc>89] = np.nan
    radius = np.sqrt(x_gal**2 + y_gal**2)
    azang  = np.degrees(np.arctan2(y_gal, x_gal))
    return radius, azang


# Convert Halpha intensity to A_V-corrected SFR surface density
def sfr_ha(flux_ha, flux_hb, name='sig_sfr'):
    # TODO: Return A_Ha column as well.
    # Extinction curve from Cardelli+(1989).
    K_Ha = 2.53
    K_Hb = 3.61
    # Eq(1) from Catalan-Torrecilla+(2015). 
    A_Ha = K_Ha/(-0.4*(K_Ha-K_Hb)) * np.log10((flux_ha/flux_hb)/2.86)
    # Do not apply negative extinction.
    A_Ha[A_Ha < 0] = 0.
    flux_ha_cor = flux_ha * 10**(0.4*A_Ha)
    # input line flux is actually flux per arcsec^2
    sterad = (u.sr/u.arcsec**2).decompose()   # 206265^2
    sb_ha  = flux_ha_cor * sterad   # flux per steradian
    lsd_ha = 4*np.pi * sb_ha
    # Eq(4) from Catalan-Torrecilla+(2015).
    lumcon = 5.5e-42 * (u.solMass/u.yr) / (u.erg/u.s)
    sig_sfr = (lumcon * lsd_ha).to(u.solMass/(u.pc**2*u.Gyr))
    if isinstance(flux_ha, Column) and isinstance(flux_hb, Column):
        return Column(sig_sfr, name=name)
    else:
        return sig_sfr
    

# Convert CO intensity to H2(+He) surface density
def msd_co(sb_co, alphaco=4.3, name='sig_mol'):
    convfac = alphaco * (u.solMass/u.pc**2) / (u.K*u.km/u.s)
    sig_mol = (convfac*sb_co).to(u.solMass/u.pc**2)
    if isinstance(sb_co, Column):
        return Column(sig_mol, name=name)
    else:
        return sig_mol
    

# Convert units for stellar surface density
def stmass_pc2(stmass_as2, dist=10*u.Mpc, name='sig_star'):
    sterad = (u.sr/u.arcsec**2).decompose()   # 206265^2
    pxarea = (dist**2/sterad).to(u.pc**2)
    if isinstance(stmass_as2, Column):
        stmass_pc2 = 10**np.array(stmass_as2) * u.solMass / pxarea
        stmass_pc2[~np.isfinite(stmass_pc2)] = np.nan
        return Column(stmass_pc2, name=name)
    else:
        stmass_pc2 = 10**stmass_as2 * u.solMass / pxarea
        stmass_pc2[~np.isfinite(stmass_pc2)] = np.nan
        return stmass_pc2


# return log10(a/b), taking care of -InF values from the logarithm. 
def ulogratio(a, b, ae = 0.0, be = 0.0): 
    try: 
        ua = ufloat(a, ae)
        ub = ufloat(b, be)
        logr = unp.log10(ua) - unp.log10(ub)
        return logr.n, logr.s
    except:
        return np.nan, np.nan


# BPT classification, see Husemann et al. (2013) Figure 7.
def bpt_type(flux_nii, flux_oiii, flux_ha, flux_hb, ew_ha):
    # TODO: trap bad values before taking log
    n2ha = np.log10(flux_nii)  - np.log10(flux_ha)
    o3hb = np.log10(flux_oiii) - np.log10(flux_hb)    

    kewley01 = lambda nii: 1.19 + 0.61/(nii - 0.47)
    kauffm03 = lambda nii: 1.30 + 0.61/(nii - 0.05)
    cidfer10 = lambda nii: 0.48 + 1.01*nii

    BPT = np.full(len(n2ha), np.nan)
    sf = (n2ha > -1.5) & (n2ha < -0.1) & (o3hb < kauffm03(n2ha)) & (abs(ew_ha) > 6.0)
    BPT[sf] = -1
    inter = (~sf) & (n2ha < 0.3) & (o3hb < kewley01(n2ha))
    BPT[inter] = 0
    liner = (~sf) & (~inter) & (o3hb > -1) & (o3hb < cidfer10(n2ha))
    BPT[liner] = 1
    seyfert = (~sf) & (~inter) & (~liner) & (o3hb > -1)
    BPT[seyfert] = 2

#     BPT = np.zeros(len(n2ha))
#     for i in range(len(n2ha)):
#         if (n2ha[i] > -1.5 and n2ha[i] < -0.1 and 
#                 o3hb[i] < kauffm03(n2ha[i]) and abs(ew_ha[i]) > 6.0):
#             BPT[i] = -1  # Starforming, below Kauffmann line
#         elif n2ha[i] < 0.3 and o3hb[i] < kewley01(n2ha[i]):
#             BPT[i] = 0   # Intermediate, between Kewley & Kauffmann
#         elif o3hb[i] > -1  and o3hb[i] < cidfer10(n2ha[i]):
#             BPT[i] = 1   # LINER
#         elif o3hb[i] > -1:
#             BPT[i] = 2   # Seyfert
#         else:
#             BPT[i] = np.nan
    return BPT


# Metallicity derived from O3N2 line ratio, Marino+13 calibration.
# Require star-forming in BPT diagram.
# Input is a table containing the appropriate columns.
def ZOH_o3n2(fluxtab, name='ZOH', err=False):
    
    nelt = len(fluxtab['flux_[NII]6583'])
    uN2F = unp.uarray(fluxtab['flux_[NII]6583'], fluxtab['e_flux_[NII]6583'])
    uO3F = unp.uarray(fluxtab['flux_[OIII]5007'], fluxtab['e_flux_[OIII]5007'])
    uHaF = unp.uarray(fluxtab['flux_Halpha'], fluxtab['e_flux_Halpha'])
    uHbF = unp.uarray(fluxtab['flux_Hbeta'], fluxtab['e_flux_Hbeta'])
    
    uO3N2 = unp.uarray(np.full(nelt, np.nan),np.full(nelt, np.nan))
#    good = (~unp.isnan(uN2F)) & (~unp.isnan(uO3F)) & (~unp.isnan(uHaF)) & (~unp.isnan(uHbF))
    good = ((unp.nominal_values(uN2F)>0) & (unp.nominal_values(uO3F)>0) 
            & (unp.nominal_values(uHaF)>0) & (unp.nominal_values(uHbF)>0))
    uO3N2[good] = (unp.log10(uO3F[good]) - unp.log10(uHbF[good]) 
                    - (unp.log10(uN2F[good]) - unp.log10(uHaF[good])))

    BPT = bpt_type(fluxtab['flux_[NII]6583'], fluxtab['flux_[OIII]5007'], 
            fluxtab['flux_Halpha'], fluxtab['flux_Halpha'], fluxtab['EW_Halpha'])
            
    uOH_M13 = 8.533 - 0.214 * uO3N2
    uOH_M13[BPT != -1] = ufloat(np.nan, np.nan)

    if err: 
        return (Column(unp.nominal_values(uOH_M13), name=name), 
                Column(unp.std_devs(uOH_M13), name=name+'_err'))
    else:            
        return Column(unp.nominal_values(uOH_M13), name=name)


# Metallicity derived from N2 line ratio, Marino+13 calibration.
# Input is a table containing the appropriate columns.
def ZOH_n2(fluxtab, err=False):
    nelt = len(fluxtab['flux_[NII]6583'])
    uN2F = unp.uarray(fluxtab['flux_[NII]6583'], fluxtab['e_flux_[NII]6583'])
    uHaF = unp.uarray(fluxtab['flux_Halpha'], fluxtab['e_flux_Halpha'])

    uN2 = unp.uarray(np.full(nelt, np.nan),np.full(nelt, np.nan))
    good = ((unp.nominal_values(uN2F)>0) & (unp.nominal_values(uHaF)>0))
    uN2[good] = (unp.log10(uN2F[good]) - unp.log10(uHaF[good]))

    BPT = bpt_type(fluxtab['flux_[NII]6583'], fluxtab['flux_[OIII]5007'], 
            fluxtab['flux_Halpha'], fluxtab['flux_Halpha'], fluxtab['EW_Halpha'])
            
    uOH_N2 = 8.743 + 0.462*uN2  # Eq(4) from Marino+2013
    uOH_N2[BPT != -1] = ufloat(np.nan, np.nan)

    if err: 
        return unp.std_devs(uOH_N2)
    else:            
        return unp.nominal_values(uOH_N2)


# Prepare a 2D histogram from a scatterplot
def xy2hist(xarr, yarr, log=True, bins=[100,100]):
    if log:
        x = np.log10(xarr)
        y = np.log10(yarr)
    else:
        x = xarr
        y = yarr
    # Histogram the data
    # https://stackoverflow.com/questions/49662964/density-scatter-plot-for-huge-dataset-in-matplotlib
    hh, locx, locy = np.histogram2d(x, y, bins=bins)
    # Get the bin value for each point
    z = np.array([hh[np.argmax(a<=locx[1:]),np.argmax(b<=locy[1:])] for a,b in zip(x,y)])
    idx = z.argsort()
    x, y, z = x[idx], y[idx], z[idx]
    if log:
        z = np.log10(z)
    return x, y, z, hh, locx, locy