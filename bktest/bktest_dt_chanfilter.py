import sys
import misc
import data_handler as dh
import pandas as pd
import numpy as np
import trade_position as tradepos
import datetime
import json

def dual_thrust_sim( mdf, config):
    ddf = config['ddf']
    close_daily = config['close_daily']
    offset = config['offset']
    k = config['param'][0]
    win = config['param'][1]
    multiplier = config['param'][2]
    f = config['param'][3]
    ep_enabled = config['EP']
    chan = config['chan']
    chan_func = config['chan_func']
    tcost = config['trans_cost']
    unit = config['unit']
    SL = config['stoploss']
    min_rng = config['min_range']
    no_trade_set = config['no_trade_set']
    if win == -1:
        tr= pd.concat([ddf.high - ddf.low, ddf.close - ddf.close.shift(1)], 
                       join='outer', axis=1).max(axis=1).shift(1)
    elif win == 0:
        tr = pd.concat([(pd.rolling_max(ddf.high, 2) - pd.rolling_min(ddf.close, 2))*multiplier, 
                        (pd.rolling_max(ddf.close, 2) - pd.rolling_min(ddf.low, 2))*multiplier,
                        ddf.high - ddf.close, 
                        ddf.close - ddf.low], 
                        join='outer', axis=1).max(axis=1).shift(1)
    else:
        tr= pd.concat([pd.rolling_max(ddf.high, win) - pd.rolling_min(ddf.close, win), 
                       pd.rolling_max(ddf.close, win) - pd.rolling_min(ddf.low, win)], 
                       join='outer', axis=1).max(axis=1).shift(1)
    ddf['TR'] = tr
    ddf['MA'] = pd.rolling_mean(ddf.close, chan).shift(1)
    ddf['H1'] = eval(chan_func['high']['func'])(ddf, chan, **chan_func['high']['args']).shift(1)
    ddf['L1'] = eval(chan_func['low']['func'])(ddf, chan, **chan_func['low']['args']).shift(1)
    ll = mdf.shape[0]
    mdf['pos'] = 0
    mdf['cost'] = 0
    curr_pos = []
    closed_trades = []
    start_d = ddf.index[0]
    end_d = mdf.index[-1].date()
    prev_d = start_d - datetime.timedelta(days=1)
    tradeid = 0
    for dd in mdf.index:
        mslice = mdf.loc[dd]
        min_id = mslice.min_id
        d = mslice.date
        dslice = ddf.loc[d]
        if np.isnan(dslice.TR) or (mslice.close == 0):
            continue
        if len(curr_pos) == 0:
            pos = 0
        else:
            pos = curr_pos[0].pos
        mdf.set_value(dd, 'pos', pos)
        d_open = dslice.open
        if (d_open <= 0):
            continue
        rng = max(min_rng * d_open, k * dslice.TR)
        if (prev_d < d):
            d_open = mslice.open
            d_high = mslice.high
            d_low =  mslice.low
        else:
            d_open = dslice.open
            d_high = max(d_high, mslice.high)
            d_low  = min(d_low, mslice.low)
        prev_d = d
        buytrig  = d_open + rng
        selltrig = d_open - rng
        if dslice.MA > mslice.close:
            buytrig  += f * rng
        elif dslice.MA < mslice.close:
            selltrig -= f * rng
        if ep_enabled:
            buytrig = max(buytrig, d_high)
            selltrig = min(selltrig, d_low)
        if (min_id >= config['exit_min']) :
            if (pos != 0) and (close_daily or (d == end_d)):
                curr_pos[0].close(mslice.close - misc.sign(pos) * offset , dd)
                tradeid += 1
                curr_pos[0].exit_tradeid = tradeid
                closed_trades.append(curr_pos[0])
                curr_pos = []
                mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
                pos = 0
        elif min_id not in no_trade_set:
            if (pos!=0) and (SL>0):
                curr_pos[0].trail_update(mslice.close)
                if curr_pos[0].check_exit(mslice.close, SL*mslice.close):
                    curr_pos[0].close(mslice.close-offset*misc.sign(pos), dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
                    pos = 0
            if (mslice.high >= buytrig) and (pos <=0 ):
                if len(curr_pos) > 0:
                    curr_pos[0].close(mslice.close+offset, dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
                if mslice.high >= dslice.H1:
                    new_pos = tradepos.TradePos([mslice.contract], [1], unit, mslice.close + offset, mslice.close + offset)
                    tradeid += 1
                    new_pos.entry_tradeid = tradeid
                    new_pos.open(mslice.close + offset, dd)
                    curr_pos.append(new_pos)
                    pos = unit
                    mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
            elif (mslice.low <= selltrig) and (pos >=0 ):
                if len(curr_pos) > 0:
                    curr_pos[0].close(mslice.close-offset, dd)
                    tradeid += 1
                    curr_pos[0].exit_tradeid = tradeid
                    closed_trades.append(curr_pos[0])
                    curr_pos = []
                    mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
                if mslice.low <= dslice.L1:
                    new_pos = tradepos.TradePos([mslice.contract], [1], -unit, mslice.close - offset, mslice.close - offset)
                    tradeid += 1
                    new_pos.entry_tradeid = tradeid
                    new_pos.open(mslice.close - offset, dd)
                    curr_pos.append(new_pos)
                    pos = -unit
                    mdf.set_value(dd, 'cost', mdf.at[dd, 'cost'] - abs(pos) * (offset + mslice.close*tcost))
        mdf.set_value(dd, 'pos', pos)
    return (mdf, closed_trades)

def gen_config_file(filename):
    sim_config = {}
    sim_config['sim_func']  = 'bktest_dt_chanfilter.dual_thrust_sim'
    sim_config['scen_keys'] = ['chan', 'param']
    sim_config['sim_name']   = 'DTdchan_'
    sim_config['products']   = ['y', 'p', 'l', 'pp', 'cs', 'a', 'rb', 'SR', 'TA', 'MA', 'i', 'j', 'jd', 'jm', 'ag', 'cu', 'm', 'RM', 'ru']
    sim_config['start_date'] = '20141101'
    sim_config['end_date']   = '20160219'
    sim_config['need_daily'] = True
    sim_config['param']  =  [
            (0.5, 0, 0.5, 0.0), (0.6, 0, 0.5, 0.0), (0.7, 0, 0.5, 0.0), (0.8, 0, 0.5, 0.0), \
            (0.9, 0, 0.5, 0.0), (1.0, 0, 0.5, 0.0), (1.1, 0, 0.5, 0.0), \
            (0.5, 1, 0.5, 0.0), (0.6, 1, 0.5, 0.0), (0.7, 1, 0.5, 0.0), (0.8, 1, 0.5, 0.0), \
            (0.9, 1, 0.5, 0.0), (1.0, 1, 0.5, 0.0), (1.1, 1, 0.5, 0.0), \
            (0.25,2, 0.5, 0.0), (0.3, 2, 0.5, 0.0), (0.35, 2, 0.5, 0.0), (0.4, 2, 0.5, 0.0), \
            (0.45, 2, 0.5, 0.0),(0.5, 2, 0.5, 0.0), \
            (0.2, 4, 0.5, 0.0), (0.25, 4, 0.5, 0.0),(0.3, 4, 0.5, 0.0), (0.35, 4, 0.5, 0.0),\
            #(0.4, 4, 0.5, 0.0), (0.45, 4, 0.5, 0.0),(0.5, 4, 0.5, 0.0),\
            ]
    sim_config['chan'] = [10, 20]
    sim_config['pos_class'] = 'tradepos.TradePos'
    sim_config['proc_func'] = 'dh.day_split'
    sim_config['offset']    = 1
    chan_func = { 'high': {'func': 'dh.PCT_CHANNEL', 'args':{'pct': 90, 'field': 'high'}},
                  'low':  {'func': 'dh.PCT_CHANNEL', 'args':{'pct': 10, 'field': 'low'}}}
    config = {'capital': 10000,
              'use_chan': True,
              'trans_cost': 0.0,
              'close_daily': False,
              'unit': 1,
              'stoploss': 0.0,
              'min_range': 0.0035,
              'proc_args': {'minlist':[1500]},
              'pos_args': {},
              'pos_update': False,
              'EP': False,
              'chan_func': chan_func,
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
