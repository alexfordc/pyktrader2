import agent
import saveagent
import datetime
import sys
import time
import logging
import mysqlaccess
import misc
import base
import json
from gui_agent import *

def get_option_map(underliers, expiries, strikes):
    opt_map = {}
    for under, expiry, ks in zip(underliers, expiries, strikes):
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

def save(name, config_file, tday, filter):
    base.config_logging(name + "\\" + name + ".log", level=logging.DEBUG,
                   format = '%(name)s:%(funcName)s:%(lineno)d:%(asctime)s %(levelname)s %(message)s',
                   to_console = True,
                   console_level = logging.INFO)
    scur_day = datetime.datetime.strptime(tday, '%Y%m%d').date()
    filter_flag = (int(filter)>0)
    with open(config_file, 'r') as infile:
        config = json.load(infile)
    save_agent = saveagent.SaveAgent(name = name, tday = scur_day, config = config)
    curr_insts = misc.filter_main_cont(tday, filter_flag)
    for inst in curr_insts:
        save_agent.add_instrument(inst)
    try:
        save_agent.restart()
        while 1:
            time.sleep(1)
    except KeyboardInterrupt:
        save_agent.exit()

def run_gui(name, config_file, tday, agent_class = 'agent.Agent'):
    base.config_logging(name + "\\" + name + ".log", level=logging.DEBUG,
                   format = '%(name)s:%(funcName)s:%(lineno)d:%(asctime)s %(levelname)s %(message)s',
                   to_console = True,
                   console_level = logging.INFO)
    scur_day = datetime.datetime.strptime(tday, '%Y%m%d').date()
    myApp = MainApp(name, scur_day, config_file, agent_class = agent_class, master = None)
    myGui = Gui(myApp)
    # myGui.iconbitmap(r'c:\Python27\DLLs\thumbs-up-emoticon.ico')
    myGui.mainloop()

def run(name, config_file, tday, agent_class = 'agent.Agent'):
    base.config_logging(name + "\\" + name + ".log", level=logging.DEBUG,
                   format = '%(name)s:%(funcName)s:%(lineno)d:%(asctime)s %(levelname)s %(message)s',
                   to_console = True,
                   console_level = logging.INFO)
    scur_day = datetime.datetime.strptime(tday, '%Y%m%d').date()
    cls_str = agent_class.split('.')
    with open(config_file, 'r') as infile:
        config = json.load(infile)
    agent_cls = getattr(__import__(str(cls_str[0])), str(cls_str[1]))
    agent = agent_cls(name=name, tday=scur_day, config=config)
    try:
        agent.restart()
        while 1:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.exit()

if __name__ == '__main__':
    args = sys.argv[1:]
    app_name = args[0]
    params = (args[1], args[2], args[3], args[4], )
    getattr(sys.modules[__name__], app_name)(*params)