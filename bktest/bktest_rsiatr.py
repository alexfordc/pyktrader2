import os,sys,inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
import json
import misc
import data_handler as dh
import pandas as pd
import numpy as np
import datetime
from backtest import *

class RSIATRSim(StratSim):
    def __init__(self, config):
        super(RSIATRSim, self).__init__(config)

    def process_config(self, config): 
        self.close_daily = config['close_daily']
        self.offset = config['offset']
        self.freq = config['freq']
        self.atr_len = config['atr_period']
        self.atrma_len = config['atrma_period']        
        self.rsi_len = config['rsi_len']
        self.rsi_trigger = config['rsi_trigger']
        self.pos_update = config['pos_update']
        self.pos_class = config['pos_class']
        self.pos_args  = config['pos_args']        
        self.tcost = config['trans_cost']
        self.unit = config['unit']
        self.weights = config.get('weights', [1])
        self.SL = config['stoploss']
        self.no_trade_set = config['no_trade_set']
        self.pos_freq = config.get('pos_freq', 1)
        self.exit_min = config.get('exit_min', 2058)
        self.buy_trig = 0.0
        self.sell_trig = 0.0
     
    def process_data(self, mdf):
        xdf = dh.conv_ohlc_freq(mdf, self.freq) 
        xdf['ATR'] = dh.ATR(xdf, n = self.atr_len).shift(1)
        xdf['ATRMA'] = dh.MA(xdf, n=self.atrma_len, field = 'ATR')
        xdf['RSI'] = dh.RSI(xdf, n = self.rsi_len).shift(1).fillna(0)        
        self.df = xdf.fillna(method='ffill')
        self.df['datetime'] = self.df.index
        self.df['cost'] = 0
        self.df['pos'] = 0
        self.df['traded_price'] = self.df['open']

    def daily_initialize(self, sim_data, n):
        pass

    def check_data_invalid(self, sim_data, n):
        return (sim_data['atr'][n] == 0) or (sim_data['atrma'][n] == 0) or (sim_data['rsi'][n] == 0) \
               or (sim_data['date'][n] != sim_data['date'][n + 1])

    def get_tradepos_exit(self, sim_data, n):
        return self.SL * sim_data['atr'][n]

    def on_bar(self, sim_data, n):
        self.pos_args = {'reset_margin': sim_data['atr'][n]}        
        target_pos = (sim_data['rsi'][n] > 100 - self.rsi_trigger) - (sim_data['rsi'][n] < self.sell_trig)
        curr_pos = 0
        if len(self.positions)>0:
            curr_pos = self.positions[0].pos
            need_close = (self.close_daily or (self.scur_day == sim_data['date'][-1])) and (sim_data['min_id'][n] >= self.exit_min)
            for tradepos in self.positions:
                if need_close or (tradepos.pos * target_pos < 0):
                    self.close_tradepos(tradepos, sim_data['open'][n+1])
            self.positions = [pos for pos in self.positions if not pos.is_closed]
            if need_close:
                return        
        if target_pos != 0 and (curr_pos * target_pos <= 0):
            if curr_pos != 0:
                self.close_tradepos(tradepos, sim_data['open'][n+1])            
            self.open_tradepos([sim_data['contract'][n]], sim_data['open'][n+1], target_pos)

def gen_config_file(filename):
    sim_config = {}
    sim_config['sim_class']  = 'bktest_rsiatr.RSIATRSim'
    sim_config['sim_func'] = 'run_loop_sim'
    sim_config['scen_keys'] = ['freq', '', 'stoploss']
    sim_config['sim_name']   = 'RSI_ATR'
    sim_config['products']   = ['m', 'RM', 'y', 'p', 'a', 'rb', 'SR', 'TA', 'MA', 'i', 'ru', 'j' ]
    sim_config['start_date'] = '20160102'
    sim_config['end_date']   = '20170407'
    sim_config['stoploss'] = [1, 2, 3]
    sim_config['freq'] = ['3min', '5min', '15min']
    sim_config['pos_class'] = 'strat.TargetTrailTradePos'
    sim_config['proc_func'] = 'dh.day_split'
    sim_config['offset']    = 1

    config = {'capital': 10000,
              'trans_cost': 0.0,
              'close_daily': False,
              'unit': 1,                           
              'pos_args': {},
              'pos_update': True,
              'atr_period': 22,
              'atrma_period': 10, 
              'rsi_len': 5,
              }
    sim_config['config'] = config
    with open(filename, 'w') as outfile:
        json.dump(sim_config, outfile)
    return sim_config

if __name__=="__main__":
    args = sys.argv[1:]
    if len(args) < 1:
        print "need to input a file name for config file"
    else:
        gen_config_file(args[0])
    pass
