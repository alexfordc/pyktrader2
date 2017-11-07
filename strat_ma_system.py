#-*- coding:utf-8 -*-
from base import *
from misc import *
import data_handler as dh
import copy
from strategy import *
 
class MASystemTrader(Strategy):
    common_params =  dict( Strategy.common_params, **{'channel_keys': ['DONCH_HC', 'DONCH_LC'], 'ma_key': 'MA_CLOSE', \
                                                      'price_limit_buffer': 5, \
                                                      'data_func': [['MA_CLOSE_', 'dh.MA', 'dh.ma'], \
                                                                    ["DONCH_HH", "dh.DONCH_H", "dh.donch_h", {'field':'high'}], \
                                                                    ["DONCH_LL", "dh.DONCH_L", "dh.donch_l", {'field':'low'}]]})
    asset_params = dict({'ma_win': [10, 20, 40], 'freq': 30, 'channels': 20, }, **Strategy.asset_params)
    def __init__(self, config, agent = None):
        Strategy.__init__(self, config, agent)
        numAssets = len(self.underliers)
        self.chan_high = [0.0] * numAssets
        self.chan_low  = [0.0] * numAssets
        self.ma_prices = [[]] * numAssets
        self.tick_base = [0.0] * numAssets
        self.ma_fast = [0.0] * numAssets
        self.ma_slow = [0.0] * numAssets
        self.ma_medm = [0.0] * numAssets
        self.daily_close_buffer = 3

    def register_func_freq(self):
        for idx, under in enumerate(self.underliers):            
            for idy, infunc in enumerate(self.data_func):
                name  = infunc[0]
                sfunc = eval(infunc[1])
                rfunc = eval(infunc[2])
                if len(infunc) > 3:
                    fargs = infunc[3]
                else:
                    fargs = {}
                freq_str = str(self.freq[idx]) + 'm'
                if idy == 0:
                    for win in self.ma_win[idx]:
                        fobj = BaseObject(name = name + str(win), sfunc = fcustom(sfunc, n = win, **fargs), rfunc = fcustom(rfunc, n = win, **fargs))
                        self.agent.register_data_func(under[0], freq_str, fobj)
                else:
                    chan = self.channels[idx]
                    if chan > 0:
                        fobj = BaseObject(name = name + str(chan), sfunc = fcustom(sfunc, n = chan, **fargs), rfunc = fcustom(rfunc, n = chan, **fargs))
                        self.agent.register_data_func(under[0], freq_str, fobj)

    def register_bar_freq(self):
        for idx, under in enumerate(self.underliers):
            inst = under[0]
            if self.freq[idx] > 0:
                self.agent.inst2strat[inst][self.name].append(self.freq[idx])

    def initialize(self):
        self.load_state()
        for idx, underlier in enumerate(self.underliers):
            inst = underlier[0]
            self.tick_base[idx] = self.agent.instruments[inst].tick_base
            min_id = self.agent.instruments[inst].last_tick_id/1000
            min_id = int(min_id/100)*60 + min_id % 100 - self.daily_close_buffer
            self.last_min_id[idx] = int(min_id/60)*100 + min_id % 60
            self.update_mkt_state(idx)
        self.update_trade_unit()

    def update_mkt_state(self, idx):
        instID = self.underliers[idx][0]
        xdf = self.agent.min_data[instID][self.freq[idx]].data
        self.ma_prices[idx] = [ xdf[self.ma_key + '_' + str(win)][-1] for win in self.ma_win[idx]]
        self.ma_fast[idx] = self.ma_prices[idx][0]
        self.ma_slow[idx] = self.ma_prices[idx][-1]
        self.ma_medm[idx] = self.ma_prices[idx][1]
        if self.channels[idx] > 0:
            key = self.channel_keys[0] + str(self.channels[idx])
            self.chan_high[idx] = xdf[key][-2]
            key = self.channel_keys[1] + str(self.channels[idx])
            self.chan_low[idx] = xdf[key][-2]

    def on_bar(self, idx, freq):
        inst = self.underliers[idx][0]
        self.update_mkt_state(idx)
        self.check_trigger(idx)

    def on_tick(self, idx, ctick):
        pass

    def check_trigger(self, idx):
        if len(self.submitted_trades[idx]) > 0:
            return
        inst = self.underliers[idx][0]
        min_id = self.agent.cur_min[inst]['tick_min']
        num_pos = len(self.positions[idx])
        buysell = 0
        if num_pos > 0:
            buysell = self.positions[idx][0].direction
        tick_base = self.tick_base[idx]
        save_status = False
        curr_p = self.curr_prices[idx]
        high_chan = (self.channels[idx] <= 0) or (curr_p >= self.chan_high[idx])
        low_chan = (self.channels[idx] <= 0) or (curr_p <= self.chan_low[idx])
        if (min_id >= self.last_min_id[idx]):
            if (buysell!=0) and (self.close_tday[idx]):
                msg = 'MA_%s to close position before EOD for inst = %s, direction=%s, volume=%s, current tick_id = %s' \
                        % (len(self.ma_prices[idx]), inst, buysell, self.trade_unit[idx], min_id)
                self.close_tradepos(idx, self.positions[idx][0], self.curr_prices[idx] - buysell * tick_base)
                self.status_notifier(msg)
                save_status = True
            return save_status
        if ((buysell > 0) and (self.ma_fast[idx] < self.ma_slow[idx])) or ((buysell < 0) and (self.ma_fast[idx] > self.ma_slow[idx])):
            msg = 'MA_%s to close position after hitting MA line for inst = %s, direction=%s, volume=%s, MA=%s, current data = %s' \
                    % (len(self.ma_prices[idx]), inst, buysell, self.trade_unit[idx], self.ma_prices[idx], self.agent.min_data[inst][self.freq[idx]].data[-1])
            self.close_tradepos(idx, self.positions[idx][0], self.curr_prices[idx] - buysell * tick_base)
            self.status_notifier(msg)
            save_status = True
            buysell = 0
        if (self.trade_unit[idx] > 0) and (buysell == 0):
            if (self.ma_fast[idx] >= self.ma_medm[idx]) and (self.ma_fast[idx] >= self.ma_slow[idx]) and high_chan:
                buysell = 1
            elif (self.ma_fast[idx] <= self.ma_medm[idx]) and (self.ma_fast[idx] <= self.ma_slow[idx]) and low_chan:
                buysell = -1
            if buysell != 0:
                msg = 'MA_%s to open position for inst = %s, chan_high=%s, chan_low=%s, MA=%s, curr_price= %s, direction=%s, volume=%s' \
                                        % (len(self.ma_prices[idx]), inst, self.chan_high[idx], self.chan_low[idx], self.ma_prices[idx], self.curr_prices[idx], buysell, self.trade_unit[idx])
                self.open_tradepos(idx, buysell, self.curr_prices[idx] + buysell * tick_base)
                self.status_notifier(msg)
                save_status = True
        return save_status
