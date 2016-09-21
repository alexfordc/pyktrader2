#-*- coding:utf-8 -*-
from base import *
from misc import *
import data_handler as dh
import copy
from strategy import *
 
class DTSplitChanAddon(Strategy):
    common_params =  dict({'open_period': [300, 1500, 2100], 'channel_keys': ['DONCH_HH', 'DONCH_LL'], 'price_limit_buffer': 5}, **Strategy.common_params)
    asset_params = dict({'lookbacks': 1, 'ratios': 1.0, 'freq': 1, 'channels': 20, 'addon_ratio': 1.0, 'min_rng': 0.004, 'daily_close': False, }, **Strategy.asset_params)
    def __init__(self, config, agent = None):
        Strategy.__init__(self, config, agent)
        numAssets = len(self.underliers)
        self.cur_rng = [0.0] * numAssets
        self.chan_high = [0.0] * numAssets
        self.chan_low  = [0.0] * numAssets
        self.tday_open = [0.0] * numAssets
        self.tick_base = [0.0] * numAssets
        self.open_idx = [0] * numAssets
        self.daily_close_buffer = 3
        self.num_tick = 1

    def register_func_freq(self):
        for under, chan in zip(self.underliers, self.channels):
            if chan <= 0:
                continue
            for infunc in self.data_func:
                name  = infunc[0]
                sfunc = eval(infunc[1])
                rfunc = eval(infunc[2])
                if len(infunc) > 3:
                    fargs = infunc[3]
                else:
                    fargs = {}
                fobj = BaseObject(name = name + str(chan), sfunc = fcustom(sfunc, n = chan, **fargs), rfunc = fcustom(rfunc, n = chan, **fargs))
                self.agent.register_data_func(under[0], 'd', fobj)

    def register_bar_freq(self):
        for idx, under in enumerate(self.underliers):
            inst = under[0]
            self.agent.inst2strat[inst][self.name].append(1)
            if self.freq[idx] > 1:
                self.agent.inst2strat[inst][self.name].append(self.freq[idx])
            #self.logger.debug("stat = %s register bar event for inst=%s freq = 1" % (self.name, inst, ))

    def initialize(self):
        self.load_state()
        for idx, underlier in enumerate(self.underliers):
            inst = underlier[0]
            self.tick_base[idx] = self.agent.instruments[inst].tick_base
            min_id = self.agent.instruments[inst].last_tick_id/1000
            min_id = int(min_id/100)*60 + min_id % 100 - self.daily_close_buffer
            self.last_min_id[idx] = int(min_id/60)*100 + min_id % 60
            ddf = self.agent.day_data[inst].data
            mdf = self.agent.min_data[inst][1].data
            min_date = mdf['date'][-1]
            last_date = ddf['date'][-1]
            if self.channels[idx]>0:
                key = self.channel_keys[0] + str(self.channels[idx])
                self.chan_high[idx] = ddf[key][-1]
                key = self.channel_keys[1] + str(self.channels[idx])
                self.chan_low[idx]  = ddf[key][-1]
            if last_date < min_date:
                last_min = mdf['min_id'][-1]
                pid = 0
                for i in range(1, len(self.open_period)):
                    if self.open_period[i] > last_min:
                        pid = i - 1
                        break
                self.open_idx[idx] = pid
                midx = len(mdf)-1
                for i in range(len(mdf)-2, -1, -1):
                    if (mdf['date'][i] < min_date) or (mdf['min_id'][i] < self.open_period[pid]):
                        midx = i + 1
                        break
                self.tday_open[idx] = mdf['open'][midx]
                df = mdf[:midx]
            else:
                self.tday_open[idx] = mdf['close'][-1]
                self.open_idx[idx] = 0
                df = mdf
            self.recalc_rng(idx, df)
        self.update_trade_unit()
        self.save_state()

    def recalc_rng(self, idx, df):
        split_arr = dh.array_split_by_bar(df, split_list = self.open_period, field = 'min_id')
        win = int(self.lookbacks[idx])
        ddf = split_arr.data
        if win > 0:
            self.cur_rng[idx] = max(max(ddf['high'][-win:])- min(ddf['close'][-win:]), \
                                    max(ddf['close'][-win:]) - min(ddf['low'][-win:]))
        elif win == 0:
            self.cur_rng[idx] = max(max(ddf['high'][-2:])- min(ddf['close'][-2:]), \
                                    max(ddf['close'][-2:]) - min(ddf['low'][-2:]))
            self.cur_rng[idx] = max(self.cur_rng[idx] * 0.5, ddf['high'][-1]-ddf['close'][-1], \
                                    ddf['close'][-1]-ddf['low'][-1])
        else:
            self.cur_rng[idx] = max(ddf['high'][-1] - ddf['low'][-1], abs(ddf['close'][-1] - ddf['close'][-2]))

    def save_local_variables(self, file_writer):
        pass
    
    def load_local_variables(self, row):
        pass

    def on_bar(self, idx, freq):
        inst = self.underliers[idx][0]
        min_id = self.agent.cur_min[inst]['min_id']
        curr_min = self.agent.cur_min[inst]['tick_min']
        for i in range(self.open_idx[idx], len(self.open_period)-1):
            if (self.open_period[i+1] > curr_min):
                self.open_idx[idx] = i
                break
        pid = self.open_idx[idx]
        if (self.open_period[pid] > min_id) and (self.open_period[pid] <= curr_min):
            self.tday_open[idx] = self.agent.instruments[inst].price
            self.open_idx[idx] = pid
            self.recalc_rng(idx, self.agent.min_data[inst][1].data)
            #self.logger.info("Note: the new split open is set to %s for inst=%s for stat = %s" % (self.tday_open[idx], inst, self.name, ))
        if min_id < 300:
            return False
        if (self.freq[idx]>0) and (freq == self.freq[idx]):
            inst = self.underliers[idx][0]
            min_data = self.agent.min_data[inst][freq].data
            buy_p = min_data['high'][-1]
            sell_p = min_data['low'][-1]
            save_status = self.check_trigger(idx, buy_p, sell_p)
            return save_status

    def on_tick(self, idx, ctick):
        if self.freq[idx] == 0:
            self.check_trigger(idx, self.curr_prices[idx], self.curr_prices[idx])

    def check_trigger(self, idx, buy_price, sell_price):
        save_status = False
        if len(self.submitted_trades[idx]) > 0:
            return save_status
        inst = self.underliers[idx][0]
        if (self.tday_open[idx] <= 0.0) or (self.cur_rng[idx] <= 0) or (self.curr_prices[idx] <= 0.001):
            self.logger.warning("warning: open price =0.0 or range = 0.0 or curr_price=0 for inst=%s for stat = %s" % (inst, self.name))
            return save_status
        min_id = int(self.agent.tick_id/1000.0)
        num_pos = len(self.positions[idx])
        buysell = 0
        if num_pos > 2:
            self.logger.warning('something wrong - number of tradepos is more than 2')
            return save_status
        elif num_pos >= 1:
            buysell = self.positions[idx][0].direction
        tick_base = self.tick_base[idx]
        t_open = self.tday_open[idx]
        rng = max(self.cur_rng[idx] * self.ratios[idx], t_open * self.min_rng[idx])
        buy_trig  = min( t_open + rng, self.agent.instruments[inst].up_limit - self.price_limit_buffer * tick_base)
        sell_trig = max( t_open - rng, self.agent.instruments[inst].down_limit + self.price_limit_buffer * tick_base)
        if (min_id >= self.last_min_id[idx]):
            if (buysell!=0) and (self.close_tday[idx]):
                msg = 'DT to close position before EOD for inst = %s, direction=%s, num_pos=%s, current min_id = %s' \
                        % (inst, buysell, num_pos, min_id)
                for tp in self.positions[idx]:
                    self.close_tradepos(idx, tp, self.curr_prices[idx] - buysell * self.num_tick * tick_base)
                self.status_notifier(msg)
                save_status = True
            return save_status
        if ((buy_price >= buy_trig) and (buysell <=0)) or ((sell_price <= sell_trig) and (buysell >=0)):
            if buysell!=0:
                msg = 'DT to close position for inst = %s, open= %s, buy_trig=%s, sell_trig=%s, buy_price= %s, sell_price= %s, direction=%s, num_pos=%s' \
                                    % (inst, t_open, buy_trig, sell_trig, buy_price, sell_price, buysell, num_pos)
                for tp in self.positions[idx]:
                    self.close_tradepos(idx, tp, self.curr_prices[idx] - buysell * self.num_tick * tick_base)
                self.status_notifier(msg)
                save_status = True
                num_pos = 0
            if self.trade_unit[idx] <= 0:
                return save_status
            if  (buy_price >= buy_trig):
                buysell = 1
            else:
                buysell = -1
            if buy_price >= buy_trig or sell_price <= sell_trig:
                msg = 'DT to open position for inst = %s, open= %s, buy_trig=%s, sell_trig=%s, buy_price= %s, sell_price= %s, direction=%s, volume=%s' \
                                        % (inst, t_open, buy_trig, sell_trig, buy_price, sell_price, buysell, self.trade_unit[idx])
                self.open_tradepos(idx, buysell, self.curr_prices[idx] + buysell * self.num_tick * tick_base)
                self.status_notifier(msg)
                save_status = True
                num_pos = 1
        if (buysell!=0) and (self.channels[idx] > 0) and ((buy_price >= self.chan_high[idx]) or (sell_price <= self.chan_low[idx])):
            if (num_pos < 2) and (((buysell > 0) and (buy_price >= self.chan_high[idx])) or ((buysell < 0) and (sell_price <= self.chan_low[idx]))):
                addon_vol = int(self.addon_ratio[idx]*self.trade_unit[idx])
                msg = 'DT to add position for inst = %s, high=%s, low=%s, buy= %s, sell= %s, direction=%s, volume=%s' \
                                        % (inst, self.chan_high[idx], self.chan_low[idx], buy_price, sell_price, buysell, addon_vol)
                self.open_tradepos(idx, buysell, self.curr_prices[idx] + buysell * self.num_tick * tick_base, addon_vol)
                self.status_notifier(msg)
                save_status = True
                num_pos = 2
            if (num_pos == 2) and (((buysell > 0) and (sell_price <= self.chan_low[idx])) or ((buysell < 0) and (buy_price >= self.chan_high[idx]))):
                msg = 'DT to remove position for inst = %s, high=%s, low=%s, buy= %s, sell= %s, direction=%s, volume=%s' \
                                        % (inst, self.chan_high[idx], self.chan_low[idx], buy_price, sell_price, buysell, self.positions[idx][-1].pos)
                self.close_tradepos(idx, self.positions[idx][-1], self.curr_prices[idx] - buysell * self.num_tick * tick_base)
                self.status_notifier(msg)
                save_status = True
                num_pos = 1
        return save_status