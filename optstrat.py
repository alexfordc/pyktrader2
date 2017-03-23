#-*- coding:utf-8 -*-
'''
optstrat.py
Created on Feb 03, 2015
@author: Harvey
'''
import json
import os
import csv
import pyktlib
import mysqlaccess
import trade
import numpy as np
import pandas as pd
import data_handler as dh
from misc import *

def fut2opt(fut_inst, expiry, otype, strike):
    product = inst2product(fut_inst)
    if product == 'IF':
        optkey = fut_inst.replace('IF','IO')
    else:
        optkey = product
    if product == 'Stock':
        optkey = optkey + otype + expiry.strftime('%y%m')
    else:
        optkey + '-' + otype.upper() + '-'
    opt_inst = optkey + str(int(strike))
    return opt_inst

def get_opt_margin(fut_price, strike, type):
    return 0.0

class OptionStrategy(object):
    common_params = {'name': 'test_strat', 'underliers':['m1705', 'm1709'], 'expiries': ['20170510', '20170910'], \
                     'strikes':[2600, 2650, 2700, 2750, 2800, 2850, 2900, 2950, 3000, 3050, 3100, 3150, 3200], \
                     'underliers': [], 'accrual': 'COM', 'main_cont': 'm1705', \
                     'pos_scaler': 1.0, 'daily_close_buffer': 3, 'exec_class': 'ExecAlgo1DFixT'}
    def __init__(self, config, agent = None):
        self.load_config(config)
        nlen = len(self.expiries)
        self.DFs = [1.0] * nlen
        self.opt_dict = self.get_option_map(self.underliers, self.expiries, self.strikes)
        self.option_map = dh.DynamicRecArray(dtype = [('name', '|S50'), ('underlier', '|S50'), ('cont_mth', 'i8'),
                                                      \
                                                       ('otype', '|S10'), ('strike', 'f8'), ('multiple', 'i8'), ('df', 'f8'), \
                                                       ('out_long', 'i8'), ('out_short', 'i8'), ('margin_long', 'f8'), ('margin_short', 'f8'), \
                                                       ('pv', 'f8'), ('delta', 'f8'), ('gamma', 'f8'), ('vega', 'f8'), ('theta', 'f8'), \
                                                       ('ppv', 'f8'), ('pdelta', 'f8'), ('pgamma', 'f8'), ('pvega', 'f8'), ('ptheta', 'f8'), \
                                                       ])
        self.group_risk = None
        for inst in self.underliers:
            self.option_map.loc[inst, 'underlier'] = inst
            self.option_map.loc[inst, 'df'] = 1.0
        for key in self.opt_dict:
            inst = self.opt_dict[key]
            opt_info = {'underlier': key[0], 'cont_mth': key[1], 'otype': key[2], 'strike': key[3], 'df':1.0}
            self.option_map.loc[inst, opt_info.keys()] = pd.Series(opt_info) 
        self.instIDs = self.underliers + self.option_insts.keys()
        self.irate = 0.04
        self.agent = agent
        self.folder = ''
        self.logger = None
        self.reset()
        self.submitted_pos = dict([(inst, []) for inst in self.instIDs])
        self.is_initialized = False
        self.proxy_flag = {'delta': False, 'gamma': True, 'vega': True, 'theta': True} 
        self.hedge_config = {'order_type': OPT_MARKET_ORDER, 'num_tick':1}
        self.spot_model = False
        self.pricer = pyktlib.BlackPricer
        self.last_updated = dict([(expiry, {'dtoday':0, 'fwd':0.0}) for expiry in self.expiries])

    def dep_instIDs(self):
        return self.underliers + self.opt_dict.values()
        
    def save_config(self):
        config = {}
        d = self.__dict__
        for key in self.common_params:
            config[key] = d[key]
        config['assets'] = []
        fname = self.folder + 'config.json'
        with open(fname, 'w') as ofile:
            json.dump(config, ofile)        
    
    def load_config(self, config):
        d = self.__dict__
        for key in self.common_params:
            d[key] = config.get(key, self.common_params[key])

    def set_agent(self, agent):
        self.agent = agent
        self.folder = self.agent.folder + self.name + '_'        
        for idx, under in enumerate(self.tradables):        
            under_key = '_'.join(under)
            self.under2idx[under_key] = idx
            if len(under) > 1:
                self.underlying[idx] = self.agent.add_spread(under, self.volumes[idx], self.price_unit[idx])
            else:
                self.underlying[idx] = self.agent.instruments[under[0]]             
        
    def reset(self):
        if self.agent != None:
            self.folder = self.agent.folder + self.name + '_'
            self.logger = self.agent.logger
            for inst in self.instIDs:
                self.option_map.loc[inst, 'multiple'] = self.agent.instruments[inst].multiple
                self.option_map.loc[inst, 'cont_mth'] = self.agent.instruments[inst].cont_mth
        #self.load_state()
    
    def day_start(self):
        pass
           
    def initialize(self):
        self.load_state()
        dtoday = date2xl(self.agent.scur_day) + max(self.agent.tick_id - 600000, 0)/2400000.0
        for idx, expiry in enumerate(self.expiries):
            dexp = datetime2xl(expiry)
            self.DFs[idx] = self.get_DF(dtoday, dexp)
            fwd = self.get_fwd(idx) 
            self.last_updated[expiry]['fwd'] = fwd
            self.last_updated[expiry]['dtoday'] = dtoday
            if self.spot_model:
                self.option_map.loc[self.underliers[0], 'delta'] = 1.0
                self.option_map.loc[self.underliers[0], 'df'] = 1.0
            else:
                self.option_map.loc[self.underliers[idx], 'delta'] = self.DFs[idx]
                self.option_map.loc[self.underliers[idx], 'df'] = self.DFs[idx]
            if self.volgrids[expiry] == None:
                self.volgrids[expiry] = pyktlib.Delta5VolNode(dtoday, dexp, fwd, 0.24, 0.0, 0.0, 0.0, 0.0, self.accrual)                
            self.volgrids[expiry].setFwd(fwd)
            self.volgrids[expiry].setToday(dtoday)
            self.volgrids[expiry].setExp(dexp)
            self.volgrids[expiry].initialize()
            if self.spot_model:
                cont_mth = expiry.year * 100 + expiry.month
            else:
                cont_mth = self.agent.instruments[self.underliers[idx]].cont_mth
            indices = self.option_map[(self.option_map.cont_mth == cont_mth) & (self.option_map.otype != 0)].index
            for inst in indices:
                strike = self.option_map.loc[inst].strike
                otype  = self.option_map.loc[inst].otype
                if not self.spot_model:
                    self.option_map.loc[inst, 'df'] = self.DFs[idx]
                self.option_insts[inst] = self.pricer(dtoday, dexp, fwd, self.volgrids[expiry], strike, self.irate, otype)
                self.update_greeks(inst)
        self.update_pos_greeks()
        self.update_group_risk()
        self.update_margin()
        self.is_initialized = True
    
    def update_margin(self):
        for inst in self.instIDs:
            if inst in self.underliers:
                self.option_map.loc[inst, 'margin_long'] = self.agent.instruments[inst].calc_margin_amount(ORDER_BUY)
                self.option_map.loc[inst, 'margin_short'] = self.agent.instruments[inst].calc_margin_amount(ORDER_SELL)
            else:
                under = self.agent.instruments[inst].underlying
                under_price = self.agent.instruments[under].price
                self.option_map.loc[inst, 'margin_long'] = self.agent.instruments[inst].calc_margin_amount(ORDER_BUY, under_price)
                self.option_map.loc[inst, 'margin_short'] = self.agent.instruments[inst].calc_margin_amount(ORDER_SELL, under_price)
                 
    def update_greeks(self, inst): 
        '''update option instrument greeks'''
        #multiple = self.option_map.loc[inst, 'multiple']
        pv = self.option_insts[inst].price() 
        delta = self.option_insts[inst].delta()
        gamma = self.option_insts[inst].gamma()
        vega  = self.option_insts[inst].vega()/100.0
        theta = self.option_insts[inst].theta()
        df = self.option_map.loc[inst, 'df']
        opt_info = {'pv': pv, 'delta': delta/df, 'gamma': gamma/df/df, 'vega': vega, 'theta': theta}
        self.option_map.loc[inst, opt_info.keys()] = pd.Series(opt_info)
    
    def update_pos_greeks(self):
        '''update position greeks according to current positions'''
        keys = ['pv', 'delta', 'gamma', 'vega', 'theta']
        for key in keys:
            pos_key = 'p' + key
            self.option_map[pos_key] = self.option_map[key] * self.option_map['pos'] * self.option_map['multiple']
        
    def risk_reval(self, expiry, is_recalib=True):
        '''recalibrate vol surface per fwd move, get greeks update for instrument greeks'''
        dtoday = date2xl(self.agent.scur_day) + max(self.agent.tick_id - 600000, 0)/2400000.0
        cont_mth = expiry.year * 100 + expiry.month
        indices = self.option_map[(self.option_map.cont_mth == cont_mth) & (self.option_map.otype != 0)].index
        dexp = datetime2xl(expiry)
        idx = self.expiries.index(expiry)
        fwd = self.get_fwd(idx)
        if is_recalib:
            self.last_updated[expiry]['fwd'] = fwd
            self.last_updated[expiry]['dtoday'] = dtoday
            self.volgrids[expiry].setFwd(fwd)
            self.volgrids[expiry].setToday(dtoday)            
            self.volgrids[expiry].initialize()                
        for inst in indices:
            self.option_insts[inst].setFwd(fwd)
            self.option_insts[inst].setFwd(dtoday)
            self.update_greeks(inst)
    
    def reval_all(self):
        for expiry in self.expiries:
            self.risk_reval(expiry, is_recalib=True)
        self.update_pos_greeks()
        self.update_group_risk()
        self.update_margin()
    
    def update_group_risk(self):
        group_keys = ['cont_mth', 'ppv', 'pdelta', 'pgamma','pvega','ptheta']
        self.group_risk = self.option_map[group_keys].groupby('cont_mth').sum()
    
    def add_submitted_pos(self, etrade):
        is_added = False
        for trade in self.submitted_pos:
            if trade.id == etrade.id:
                is_added = False
                return
        self.submitted_pos.append(etrade)
        return True

    def day_finalize(self):    
        self.save_state()
        self.logger.info('strat %s is finalizing the day - update trade unit, save state' % self.name)
        self.is_initialized = False
        
    def get_option_map(self, underliers, expiries, strikes):
        opt_map = {}
        for under, expiry, ks in zip(underliers, expiries, strikes):
            exch = inst2exch(under)
            for otype in ['C', 'P']:
                for strike in ks:
                    cont_mth = int(under[-4:]) + 200000
                    key = (str(under), cont_mth, otype, strike)
                    instID = under
                    if instID[:2] == "IF":
                        instID = instID.replace('IF', 'IO')
                    instID = instID + '-' + otype + '-' + str(strike)
                    opt_map[key] = instID
        return opt_map
    
    def tick_run(self, ctick):
        pass

    def run_min(self, inst):
        pass
    
    def delta_hedger(self):
        tot_deltas = self.group_risk.pdelta.sum()
        cum_vol = 0
        if (self.spot_model == False) and (self.proxy_flag['delta']== False):
            for idx, inst in enumerate(self.underliers):
                if idx == self.main_cont: 
                    continue
                multiple = self.option_map[inst, 'multiple']
                cont_mth = self.option_map[inst, 'cont_mth']
                pdelta = self.group_risk[cont_mth, 'delta'] 
                volume = int( - pdelta/multiple + 0.5)
                cum_vol += volume
                if volume!=0:
                    curr_price = self.agent.instruments[inst].price
                    buysell = 1 if volume > 0 else -1
                    valid_time = self.agent.tick_id + 600
                    etrade = trade.XTrade( [inst], [volume], [self.hedge_config['order_type']], curr_price*buysell, [self.hedge_config['num_tick']], \
                                               valid_time, self.name, self.agent.name)
                    self.submitted_pos[inst].append(etrade)
                    self.agent.submit_trade(etrade)
        inst = self.underliers[self.main_cont]
        multiple = self.option_map[inst, 'multiple']
        tot_deltas += cum_vol
        volume = int( tot_deltas/multiple + 0.5)
        if volume!=0:
            curr_price = self.agent.instruments[inst].price
            buysell = 1 if volume > 0 else -1
            etrade = trade.XTrade( [inst], [volume], [self.hedge_config['order_type']], curr_price*buysell, [self.hedge_config['num_tick']], \
                                valid_time, self.name, self.agent.name)
            self.submitted_pos[inst].append(etrade)
            self.agent.submit_trade(etrade)
        
class EquityOptStrat(OptionStrategy):
    def __init__(self, name, underliers, expiries, strikes, agent = None):
        OptionStrategy.__init__(self, name, underliers, expiries, strikes, agent)
        self.accrual = 'SSE'
        self.proxy_flag = {'delta': True, 'gamma': True, 'vega': True, 'theta': True}
        self.spot_model = True
        self.dividends = [(datetime.date(2015,4,20), 0.0), (datetime.date(2015,11,20), 0.10)]
        
    def get_option_map(self, underliers, expiries, strikes):
        cont_mths = [expiry.year*100 + expiry.month for expiry in expiries]
        all_map = {}
        for under in underliers:
            map = mysqlaccess.get_stockopt_map(under, cont_mths, strikes)
            all_map.update(map)
        return all_map
    
    def get_fwd(self, idx):
        spot = self.agent.instruments[self.underliers[0]].price
        return spot*self.DFs[idx]
    
class IndexFutOptStrat(OptionStrategy):
    def __init__(self, name, underliers, expiries, strikes, agent = None):
        OptionStrategy.__init__(self, name, underliers, expiries, strikes, agent)
        self.accrual = 'CFFEX'
        self.proxy_flag = {'delta': True, 'gamma': True, 'vega': True, 'theta': True} 
        self.spot_model = False

class CommodOptStrat(OptionStrategy):
    def __init__(self, name, underliers, expiries, strikes, agent = None):
        OptionStrategy.__init__(self, name, underliers, expiries, strikes, agent)
        self.accrual = 'COMN1'
        self.proxy_flag = {'delta': False, 'gamma': False, 'vega': True, 'theta': True} 
        self.spot_model = False
        self.pricer = pyktlib.AmericanFutPricer  
        
class OptArbStrat(CommodOptStrat):
    def __init__(self, name, underliers, expiries, strikes, agent = None):
        CommodOptStrat.__init__(self, name, underliers, expiries, strikes, agent)
        self.callspd = dict([(exp, dict([(s, {'upbnd':0.0, 'lowbnd':0.0, 'pos':0.0}) for s in ss])) for exp, ss in zip(expiries, strikes)])
        self.putspd = dict([(exp, dict([(s, {'upbnd':0.0, 'lowbnd':0.0, 'pos':0.0}) for s in ss])) for exp, ss in zip(expiries, strikes)])
        self.bfly = dict([(exp, dict([(s, {'upbnd':0.0, 'lowbnd':0.0, 'pos':0.0}) for s in ss])) for exp, ss in zip(expiries, strikes)])
        
    def tick_run(self, ctick):         
        inst = ctick.instID

class OptSubStrat(object):
    def __init__(self, strat):
        self.strat = strat
    
    def tick_run(self, ctick):
        pass
