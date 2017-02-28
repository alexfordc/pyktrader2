import sys
import json
import misc
import data_handler as dh
import pandas as pd
import numpy as np
import datetime
import backtest

def 
def run_sim(config):
    mdf = config['mdf']
    close_daily = config['close_daily']
    offset = config['offset']
    k = config['param'][0]
    win = config['param'][1]
    multiplier = config['param'][2]
    f = config['param'][3]
    price_mode = config.get('price_mode','TP')
    pos_update = config['pos_update']
    pos_class = config['pos_class']
    pos_args  = config['pos_args']
    proc_func = config['proc_func']
    proc_args = config['proc_args']
    chan_func = config['chan_func']
    chan_high = eval(chan_func['high']['func'])
    chan_low  = eval(chan_func['low']['func'])
    tcost = config['trans_cost']
    unit = config['unit']
    SL = config['stoploss']
    min_rng = config['min_range']
    chan = config['chan']
    use_chan = config['use_chan']
    no_trade_set = config['no_trade_set']
    pos_freq = config.get('pos_freq', 1)
    xdf = proc_func(mdf, **proc_args)
    if win == -1:
        tr= pd.concat([xdf.high - xdf.low, abs(xdf.close - xdf.close.shift(1))],
                       join='outer', axis=1).max(axis=1)
    elif win == 0:
        tr = pd.concat([(pd.rolling_max(xdf.high, 2) - pd.rolling_min(xdf.close, 2))*multiplier,
                        (pd.rolling_max(xdf.close, 2) - pd.rolling_min(xdf.low, 2))*multiplier,
                        xdf.high - xdf.close,
                        xdf.close - xdf.low],
                        join='outer', axis=1).max(axis=1)
    else:
        tr= pd.concat([pd.rolling_max(xdf.high, win) - pd.rolling_min(xdf.close, win),
                       pd.rolling_max(xdf.close, win) - pd.rolling_min(xdf.low, win)],
                       join='outer', axis=1).max(axis=1)
    xdf['TR'] = tr
    xdf['chan_h'] = chan_high(xdf['high'], chan, **chan_func['high']['args'])
    xdf['chan_l'] = chan_low(xdf['low'], chan, **chan_func['low']['args'])
    xdata = pd.concat([xdf['TR'].shift(1), xdf['MA'].shift(1),
                       xdf['chan_h'].shift(1), xdf['chan_l'].shift(1),
                       xdf['open']], axis=1, keys=['tr','ma', 'chanh', 'chanl', 'dopen']).fillna(0)
    df = mdf.join(xdata, how = 'left').fillna(method='ffill')
    df['pos'] = 0
    df['cost'] = 0
    df['traded_price'] = df['open']
    sim_data = dh.DynamicRecArray(dataframe=df)
    nlen = len(sim_data)
    positions = []
    closed_trades = []
    tradeid = 0
    curr_date = None
    buytrig = selltrig = 0.0
    pos = 0
    for n in range(nlen):
        cost = 0
        sim_data['pos'][n] = pos        
        if sim_data['ma'][n] == 0 or sim_data['chan_h'] == 0 or sim_data['dopen'] == 0:
            continue
        if curr_date != sim_data['date']:
            dopen = sim_data['dopen']
            rng = max(min_rng * dopen, k * sim_data['tr'][n])
            buytrig = dopen + rng
            selltrig = dopen - rng
            if sim_data['ma'][n] > dopen:
                buytrig += f * rng
            else:
                selltrig -= f * rng
        ref_price = (sim_data['close'][n] + sim_data['high'][n] + sim_data['low'][n])/3.0 if price_mode == 'TP' else sim_data['close'][n]
        target_pos = (ref_price > buytrig) - (ref_price < selltrig)               
        if len(positions)>0:
            need_close = (close_daily and sim_data['min_id'][n] >= config['exit_min'])
            for tradepos in positions:
                ep = sim_data['low'][n] if tradepos.pos > 0 else sim_data['high'][n]                
                if need_close or tradepos.check_exit(sim_data['close'][n], 0) or ( tradepos.pos * target_pos < 0):
                    tradepos.close(sim_data['close'][n] - offset * misc.sign(tradepos.pos), sim_data['datetime'][n])
                    tradepos.exit_tradeid = tradeid
                    tradeid += 1
                    pos -= tradepos.pos
                    cost += abs(tradepos_pos) * (offset + sim_data['close'][n]*tcost)
                    closed_trades.append(tradepos)
                elif pos_update:
                    tradepos.update_price(ep)
            positions = [pos for pos in positions if not pos.is_closed]
            if need_close:
                continue
        if target_pos != 0:
            if (not use_chan) or (((ref_price > sim_data['chanh']) and target_pos > 0) or ((ref_price < sim_data['chanl']) and target_pos < 0)):
                new_pos = pos_class([mslice.contract], [1], unit * target_pos, mslice.close + target_pos * offset, buytrig, **pos_args)
                tradeid += 1
                new_pos.entry_tradeid = tradeid
                new_pos.open(sim_data['close'][n] + target_pos * offset, sim_data['datetime'][n])
                positions.append(new_pos)
                pos += unit * target_pos
                cost += abs(target_pos) * (offset + sim_data['close'][n]*tcost)
        sim_data['cost'][n] = cost
        sim_data['pos'][n] = pos
            

def dual_thrust_sim( mdf, config):
    close_daily = config['close_daily']
    marginrate = config['marginrate']
    offset = config['offset']
    k = config['param'][0]
    win = config['param'][1]
    multiplier = config['param'][2]
    f = config['param'][3]
    pos_update = config['pos_update']
    pos_class = config['pos_class']
    pos_args  = config['pos_args']
    proc_func = config['proc_func']
    proc_args = config['proc_args']
    start_equity = config['capital']
    chan_func = config['chan_func']
    chan_high = eval(chan_func['high']['func'])
    chan_low  = eval(chan_func['low']['func'])
    tcost = config['trans_cost']
    unit = config['unit']
    SL = config['stoploss']
    min_rng = config['min_range']
    chan = config['chan']
    use_chan = config['use_chan']
    no_trade_set = config['no_trade_set']
    ll = mdf.shape[0]
    xdf = proc_func(mdf, **proc_args)
    if win == -1:
        tr= pd.concat([xdf.high - xdf.low, abs(xdf.close - xdf.close.shift(1))], 
                       join='outer', axis=1).max(axis=1)
    elif win == 0:
        tr = pd.concat([(pd.rolling_max(xdf.high, 2) - pd.rolling_min(xdf.close, 2))*multiplier, 
                        (pd.rolling_max(xdf.close, 2) - pd.rolling_min(xdf.low, 2))*multiplier,
                        xdf.high - xdf.close, 
                        xdf.close - xdf.low], 
                        join='outer', axis=1).max(axis=1)
    else:
        tr= pd.concat([pd.rolling_max(xdf.high, win) - pd.rolling_min(xdf.close, win), 
                       pd.rolling_max(xdf.close, win) - pd.rolling_min(xdf.low, win)], 
                       join='outer', axis=1).max(axis=1)
    xdf['TR'] = tr
    xdf['chan_h'] = chan_high(xdf['high'], chan, **chan_func['high']['args'])
    xdf['chan_l'] = chan_low(xdf['low'], chan, **chan_func['low']['args'])
    xdf['MA'] = pd.rolling_mean(xdf.close, chan)
    xdata = pd.concat([xdf['TR'].shift(1), xdf['MA'].shift(1),
                       xdf['chan_h'].shift(1), xdf['chan_l'].shift(1),
                       xdf['open']], axis=1, keys=['TR','MA', 'chanH', 'chanL', 'dopen']).fillna(0)
    mdf = mdf.join(xdata, how = 'left').fillna(method='ffill')
    mdf['pos'] = pd.Series([0]*ll, index = mdf.index)
    mdf['cost'] = pd.Series([0]*ll, index = mdf.index)
    curr_pos = []
    closed_trades = []
    end_d = mdf.index[-1].date
    #prev_d = start_d - datetime.timedelta(days=1)
    tradeid = 0
    pos_update_idx = 0
    for idx, dd in enumerate(mdf.index):
        mslice = mdf.ix[dd]
        min_id = mslice.min_id
        min_cnt = (min_id-300)/100 * 60 + min_id % 100 + 1
        if len(curr_pos) == 0:
            pos = 0
        else:
            pos = curr_pos[0].pos
        mdf.ix[dd, 'pos'] = pos
        if (mslice.TR == 0) or (mslice.MA == 0):
            continue
        d_open = mslice.dopen
        rng = max(min_rng * d_open, k * mslice.TR)
        if (d_open <= 0):
            continue
        buytrig  = d_open + rng
        selltrig = d_open - rng
        if 'reset_margin' in pos_args:
            pos_args['reset_margin'] = mslice.TR * SL
        if mslice.MA > mslice.close:
            buytrig  += f * rng
        elif mslice.MA < mslice.close:
            selltrig -= f * rng
        if (min_id >= config['exit_min']) and (close_daily or (mslice.date == end_d)):
            if (pos != 0):
                curr_pos[0].close(mslice.close - misc.sign(pos) * offset , dd)
                tradeid += 1
                curr_pos[0].exit_tradeid = tradeid
                closed_trades.append(curr_pos[0])
                curr_pos = []
                mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost) 
                pos = 0
        elif min_id not in no_trade_set:
            if (pos!=0):
                exit_flag = False
                if (curr_pos[0].check_exit( mslice.close, 0 )):
                    curr_pos[0].close(mslice.close-offset*misc.sign(pos), dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost)    
                    pos = 0
                elif pos_update and (min_cnt % config['pos_freq'] == 0):
                    if pos > 0:
                        ep = max(mdf['high'][pos_update_idx:idx])
                    else:
                        ep = max(mdf['low'][pos_update_idx:idx])
                    curr_pos[0].update_price(ep)
                    pos_update_idx = idx
            if (mslice.high >= buytrig) and (pos <= 0 ):
                if pos < 0:
                    curr_pos[0].close(mslice.close + offset, dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost)
                    pos = 0
                if (use_chan == False) or (mslice.high > mslice.chanH):
                    new_pos = pos_class([mslice.contract], [1], unit, mslice.close + offset, selltrig, **pos_args)
                    tradeid += 1
                    new_pos.entry_tradeid = tradeid
                    new_pos.open(mslice.close + offset, dd)
                    curr_pos.append(new_pos)
                    pos = unit
                    mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost)
                    pos_update_idx = idx
            elif (mslice.low <= selltrig) and (pos >=0 ):
                if pos > 0:
                    curr_pos[0].close(mslice.close-offset, dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost)
                    pos = 0
                if (use_chan == False) or (mslice.low < mslice.chanL):
                    new_pos = pos_class([mslice.contract], [1], -unit, mslice.close - offset, buytrig, **pos_args)
                    tradeid += 1
                    new_pos.entry_tradeid = tradeid
                    new_pos.open(mslice.close - offset, dd)
                    curr_pos.append(new_pos)
                    pos = -unit
                    mdf.ix[dd, 'cost'] -= abs(pos) * (offset + mslice.close*tcost)
                    pos_update_idx = idx
        mdf.ix[dd, 'pos'] = pos
    return (mdf, closed_trades)

def gen_config_file(filename):
    sim_config = {}
    sim_config['sim_func']  = 'bktest_dtsplit_psar.dual_thrust_sim'
    sim_config['scen_keys'] = ['param']
    sim_config['sim_name']   = 'DT_psar'
    sim_config['products']   = ['m', 'RM', 'y', 'p', 'a', 'rb', 'SR', 'TA', 'MA', 'i', 'ru', 'j' ]
    sim_config['start_date'] = '20150102'
    sim_config['end_date']   = '20160311'
    sim_config['param']  =  [
            (0.5, 0, 0.5, 0.0), (0.6, 0, 0.5, 0.0), (0.7, 0, 0.5, 0.0), (0.8, 0, 0.5, 0.0), \
            (0.9, 0, 0.5, 0.0), (1.0, 0, 0.5, 0.0), (1.1, 0, 0.5, 0.0), \
            (0.5, 1, 0.5, 0.0), (0.6, 1, 0.5, 0.0), (0.7, 1, 0.5, 0.0), (0.8, 1, 0.5, 0.0), \
            (0.9, 1, 0.5, 0.0), (1.0, 1, 0.5, 0.0), (1.1, 1, 0.5, 0.0), \
            (0.2, 2, 0.5, 0.0), (0.25,2, 0.5, 0.0), (0.3, 2, 0.5, 0.0), (0.35, 2, 0.5, 0.0),\
            (0.4, 2, 0.5, 0.0), (0.45, 2, 0.5, 0.0),(0.5, 2, 0.5, 0.0), \
            #(0.2, 4, 0.5, 0.0), (0.25, 4, 0.5, 0.0),(0.3, 4, 0.5, 0.0), (0.35, 4, 0.5, 0.0),\
            #(0.4, 4, 0.5, 0.0), (0.45, 4, 0.5, 0.0),(0.5, 4, 0.5, 0.0),\
            ]
    sim_config['pos_class'] = 'strat.ParSARTradePos'
    sim_config['proc_func'] = 'dh.day_split'
    sim_config['offset']    = 1
    chan_func = {'high': {'func': 'pd.rolling_max', 'args':{}},
                 'low':  {'func': 'pd.rolling_min', 'args':{}},
                 }
    config = {'capital': 10000,
              'chan': 10,
              'use_chan': False,
              'trans_cost': 0.0,
              'close_daily': False,
              'unit': 1,
              'stoploss': 0.0,
              'min_range': 0.004,
              'proc_args': {'minlist':[1500]},
              'pos_args': { 'af': 0.02, 'incr': 0.02, 'cap': 0.2},
              'pos_update': True,
              'chan_func': chan_func,
              'pos_freq':30,
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
