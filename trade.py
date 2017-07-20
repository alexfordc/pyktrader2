#-*- coding:utf-8 -*-
import logging
from base import *
from misc import *
import itertools
import datetime
import csv
import json
import os.path
import order
from trade_executor import *

class TradeStatus:
    Pending, Ready, OrderSent, PFilled, Done, Cancelled, StratConfirm = range(7)

class OrderFillStatus:
    Empty, Partial, Full = range(3)
# Pending: trigger trade, Ready: ok to start process with zero vol, OrderSent: wait for order update

Alive_Trade_Status = [TradeStatus.Ready, TradeStatus.OrderSent, TradeStatus.PFilled, TradeStatus.Cancelled]

class XTrade(object):
    # instances = weakref.WeakSet()
    id_generator = itertools.count(int(datetime.datetime.strftime(datetime.datetime.now(), '%d%H%M%S')))
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', next(self.id_generator))
        self.instIDs = kwargs['instIDs']
        self.units = kwargs['units']
        self.vol = kwargs['vol']
        self.filled_vol = kwargs.get('filled_vol', 0)
        self.filled_price = kwargs.get('filled_price', 0.0)
        self.limit_price = kwargs['limit_price']
        self.price_unit = kwargs.get('price_unit', None)
        self.strategy = kwargs.get('strategy', 'dummy')
        self.book = kwargs.get('book', '0')
        self.status = kwargs.get('status', TradeStatus.Ready)
        self.order_dict = kwargs.get('order_dict', {})
        self.working_vol = kwargs.get('working_vol', 0)
        self.remaining_vol = self.vol - self.filled_vol - self.working_vol
        self.aggressive_level = kwargs.get('aggressiveness', 1.0)
        self.start_time = kwargs.get('start_time', 300000)
        self.end_time = kwargs.get('end_time', 2115000)
        self.algo = None
        self.agent = None
        self.underlying = None

    def set_agent(self, agent):
        self.agent = agent
        self.underlying = agent.get_underlying(self.instIDs, self.units, self.price_unit)
        self.price_unit = self.underlying.multiple

    def set_algo(self, algo):
        self.algo = algo
        self.algo.set_agent(self.agent)

    def save(self):
        return json.dumps(self, skipkeys = True)

    def calc_filled_price(self, order_dict):
        filled_prices = []
        for instID in self.instIDs:
            avg_p = 0.0
            if instID in order_dict:
                sum_vol = sum([o.filled_volume for o in order_dict[instID]])
                if sum_vol > 0:
                    avg_p = sum([o.filled_price * o.filled_volume for o in order_dict[instID]])/sum_vol
            filled_prices.append(avg_p)
        if len(self.instIDs) == 1:
            return filled_prices[0]
        else:            
            return self.underlying.price(prices=filled_prices)
            
    def refresh(self):
        if self.status not in Alive_Trade_Status:
            return self.status        
        filled_vol = []
        open_vol = 0
        total_vol = 0
        if len(self.order_dict)>0:
            for instID, unit in zip(self.instIDs, self.units):
                if instID in self.order_dict:
                    fill_vol = sum([o.filled_volume for o in self.order_dict[instID]])
                    full_vol = sum([o.volume for o in self.order_dict[instID]])
                else:
                    fill_vol = 0
                    full_vol = 0
                open_vol += full_vol - fill_vol
                total_vol += abs(unit * self.working_vol)
                filled_vol.append(fill_vol)
            self.order_filled = filled_vol
            if sum(filled_vol) >= total_vol:
                working_price = self.calc_filled_price(self.order_dict)
                working_vol = self.working_vol
                self.working_vol = 0
                self.order_dict = {}
                self.order_filled = []
                if self.status != TradeStatus.Cancelled:
                    self.status = TradeStatus.Ready
                self.on_trade(working_price, working_vol)                
            else:
                if (self.status != TradeStatus.Cancelled):
                    self.status = TradeStatus.OrderSent if open_vol > 0 else TradeStatus.PFilled
        else:
            if (self.filled_vol == self.vol) or (self.status == TradeStatus.Cancelled):
                self.set_done()
            else:
                self.status = TradeStatus.Ready            
        return self.status

    def on_trade(self, price, volume):
        new_vol = self.filled_vol + volume
        if new_vol == 0:
            return
        self.filled_price = (self.filled_price * self.filled_vol + price * volume)/new_vol
        self.filled_vol = new_vol
        self.remaining_vol = self.vol - self.working_vol - self.filled_vol
        if (self.filled_vol == self.vol) or ((self.status == TradeStatus.Cancelled) and (len(self.order_dict) == 0)):
            self.status = TradeStatus.Done
            self.algo = None
            self.update_strat()
    
    def set_done(self):
        self.status = TradeStatus.Done
        self.remaining_vol = 0
        self.working_vol = 0
        self.order_dict = {}
        self.order_filled = []
        self.algo = None
        self.update_strat()

    def update_strat(self):
        strat = self.agent.strategies[self.strategy]
        strat.on_trade(self)

    def execute(self):
        if self.algo:
            self.algo.execute()
