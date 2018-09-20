import tushare as ts
import datetime
import copy
import pandas as pd
import misc
import os
import talib
import urllib
import csv
import patoolib
import dbaccess
import json
from glob import glob
#
# from bs4 import BeautifulSoup
# from datetime import datetime
# from pandas.io.data import DataReader
#
# SITE = "http://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# START = datetime(1900, 1, 1, 0, 0, 0, 0, pytz.utc)
# END = datetime.today().utcnow()
#
#
# def scrape_list(site):
#     hdr = {'User-Agent': 'Mozilla/5.0'}
#     req = urllib2.Request(site, headers=hdr)
#     page = urllib2.urlopen(req)
#     soup = BeautifulSoup(page)
#
#     table = soup.find('table', {'class': 'wikitable sortable'})
#     sector_tickers = dict()
#     for row in table.findAll('tr'):
#         col = row.findAll('td')
#         if len(col) > 0:
#             sector = str(col[3].string.strip()).lower().replace(' ', '_')
#             ticker = str(col[0].string.strip())
#             if sector not in sector_tickers:
#                 sector_tickers[sector] = list()
#             sector_tickers[sector].append(ticker)
#     return sector_tickers
#
#
# def download_ohlc(sector_tickers, start, end):
#     sector_ohlc = {}
#     for sector, tickers in sector_tickers.iteritems():
#         print 'Downloading data from Yahoo for %s sector' % sector
#         data = DataReader(tickers, 'yahoo', start, end)
#         for item in ['Open', 'High', 'Low']:
#             data[item] = data[item] * data['Adj Close'] / data['Close']
#         data.rename(items={'Open': 'open', 'High': 'high', 'Low': 'low',
#                            'Adj Close': 'close', 'Volume': 'volume'},
#                     inplace=True)
#         data.drop(['Close'], inplace=True)
#         sector_ohlc[sector] = data
#     print 'Finished downloading data'
#     return sector_ohlc
#
#
# def store_HDF5(sector_ohlc, path):
#     with pd.get_store(path) as store:
#         for sector, ohlc in sector_ohlc.iteritems():
#             store[sector] = ohlc
#
#
# def get_snp500():
#     sector_tickers = scrape_list(SITE)
#     sector_ohlc = download_ohlc(sector_tickers, START, END)
#     store_HDF5(sector_ohlc, 'snp500.h5')

def export_tick_data(tday, folder = '', tick_id = 300000):
    all_insts, prods = dbaccess.load_alive_cont(tday)
    cnx = dbaccess.connect(**dbaccess.dbconfig)
    for inst in all_insts:
        stmt = "select * from fut_tick where instID='{prod}' and date='{cdate}' and tick_id>='{tick}'".format(prod=inst, cdate=tday.strftime('%Y-%m-%d'), tick = tick_id)
        df = pd.io.sql.read_sql(stmt, cnx)
        df.to_csv(folder + inst + '.csv', header=False, index=False)

def import_tick_data(tday, folder = ''):
    all_insts, prods = dbaccess.load_alive_cont(tday)
    cnx = dbaccess.connect(**dbaccess.dbconfig)
    cursor = cnx.cursor()
    for inst in all_insts:
        data_file = folder + inst + '.csv'
        if os.path.isfile(data_file):
            stmt = "load data local infile '{data_file}' replace into table fut_tick fields terminated by ',';".format(data_file = data_file)
            cursor.execute( stmt )
            cnx.commit()
            print inst
    cnx.close()

def import_datayes_daily_data(start_date, end_date, cont_list = [], is_replace = False):
    numdays = (end_date - start_date).days + 1
    date_list = [start_date + datetime.timedelta(days=x) for x in range(0, numdays) ]
    date_list = [ d for d in date_list if (d.weekday()< 5) and (d not in misc.CHN_Holidays)]
    for d in date_list:
        cnt = 0
        dstring = d.strftime('%Y%m%d')
        ts.set_token(misc.datayes_token)
        mkt = ts.Market()
        df = mkt.MktFutd(tradeDate = dstring)
        if len(df.ticker) == 0:
            continue
        cnx = dbaccess.connect(**dbaccess.dbconfig)
        for cont in df.ticker:
            if (len(cont_list) > 0) and (cont not in cont_list):
                continue
            data = df[df.ticker==cont]
            if len(data) == 0:
                print 'no data for %s for %s' % (cont, dstring)
            else:
                data_dict = {}
                data_dict['date']  = d
                data_dict['open']  = float(data.openPrice)
                data_dict['close'] = float(data.closePrice)
                data_dict['high']  = float(data.highestPrice)
                data_dict['low'] = float(data.lowestPrice)
                data_dict['volume'] = int(data.turnoverVol)
                data_dict['openInterest'] = int(data.openInt)
                if data_dict['volume'] > 0:
                    cnt += 1
                    dbaccess.insert_daily_data(cnx, cont, data_dict, is_replace = is_replace, dbtable = 'fut_daily')
        print 'date=%s, insert count = %s' % (d, cnt)

def extract_rar_data(source, target, extract_src = False):
    if extract_src:
        for file in os.listdir(source):
            if file.endswith(".rar"):
                patoolib.extract_archive(source+file, outdir = target)
    allrar = [y for x in os.walk(target) for y in glob(os.path.join(x[0], '*.rar'))]
    for file in allrar:
        patoolib.extract_archive(file, outdir = target)

def conv_csv_to_sql(target, db_table = 'test_fut_tick'):
    cnx = dbaccess.connect(**dbaccess.dbconfig)
    allcsvs = [y for x in os.walk(target) for y in glob(os.path.join(x[0], '*.csv'))]
    for csvfile in allcsvs:
        try:
            df = pd.DataFrame()
            df = pd.read_csv(csvfile, header = None, index_col = False, skiprows = 1, usecols = [1, 2, 3, 4, 7, 12, 13, 14,15 ])
            df.columns = ['instID', 'datetime','price', 'openInterest', 'volume', 'bidPrice1', 'askPrice1', 'bidVol1', 'askVol1']
            df['datetime'] = pd.to_datetime(df.datetime)
            df['date'] = df.datetime.apply(lambda x:x.date())
            df['hour'] = df.datetime.apply(lambda x:x.hour)
            df['min'] = df.datetime.apply(lambda x:x.minute)
            df['sec'] = df.datetime.apply(lambda x:x.second)
            df['msec'] = df.datetime.apply(lambda x:x.microsecond)/1000
            df['tick_id'] = ((df['hour'] + 6) % 24)*100000 + df['min']*1000 + df['sec']*10 + df['msec']/100
            del df['datetime']
            print csvfile, len(df)
            df.to_sql(name = db_table, flavor = 'mysql', con = cnx, if_exists='append')
            cnx.commit()
        except:
            continue
    cnx.close()
    return 0

def load_hist_csv2sql(folder, db_table):
    cnx = dbaccess.connect(**dbaccess.hist_dbconfig)
    cursor = cnx.cursor()
    allcsvs = [y for x in os.walk(folder) for y in glob(os.path.join(x[0], '*.csv'))]
    skipped_files = []
    for csvfile in allcsvs:
        try:
            str_list = csvfile.split('\\')
            filestr = str_list[-1].split('.')[0]
            fileinfo = filestr.split('_')
            trading_day = fileinfo[1]
            inst_str = fileinfo[0]
            if len(inst_str) <=4:
                print "skip %s" % csvfile
                continue
            if inst_str[-4:].isdigit():
                if int(inst_str[-4:]) < 5:
                    print "skip %s" % csvfile
                    continue
            filename = '\\\\'.join(csvfile.split('\\'))
            stmt = "load data local infile '" + filename + "' replace into table " + db_table
            stmt += " character set gb2312 fields terminated by ',' ignore 1 lines "
            stmt += "(@dummy, instID,  ts_str, price, openInterest, deltaOI, @dummy, "
            stmt += "dvol, dvol_open, dvol_close, @dummy, @dummy, "
            stmt += "bidPrice1, askPrice1, bidVol1, askVol1) "
            stmt += "set dtime = str_to_date(ts_str, '%Y-%m-%d %H:%i:%s.%f'), date = '{tdate}', ".format(tdate = trading_day)
            stmt += "hour=hour(dtime), min=minute(dtime), sec=second(dtime), msec=floor(microsecond(dtime)/1000),"
            stmt += "tick_id=mod(hour+6,24)*100000+min*1000+sec*10+floor(msec/100);"
            print csvfile
            cursor.execute(stmt)
            cnx.commit()
        except:
            print 'skip %s' % csvfile
            skipped_files.append(csvfile)
            continue
    cnx.close()
    print skipped_files
    return

def tick2ohlc(df):
    return pd.Series([df['dtime'][0], df['price'][0], df['price'].max(), df['price'].min(), df['price'][-1], df['dvol'].sum(), df['openInterest'][-1]],
                  index = ['datetime', 'open','high','low','close','volume', 'openInterest'])

def conv_tick2min(df):
    mdf = df.groupby([df['date'], df['hour'], df['min']]).apply(tick2ohlc).reset_index().set_index('datetime')
    return mdf

def min2daily(df):
    return pd.Series([df['open'][0], df['high'].max(), df['low'].min(), df['close'][-1], df['volume'].sum(), df['openInterest'][-1]],
                  index = ['open','high','low','close','volume', 'openInterest'])

def conv_min2daily(df):
    ddf = df.groupby([df['instID'], df['exch'], df['date']]).apply(min2daily).reset_index().set_index(['instID', 'exch', 'date'])
    return ddf

def conv_ohlc_freq(df, freq):
    highcol = pd.DataFrame(df['price']).resample(freq, how ='max').dropna()
    lowcol  = pd.DataFrame(df['price']).resample(freq, how ='min').dropna()
    opencol = pd.DataFrame(df['price']).resample(freq, how ='first').dropna()
    closecol= pd.DataFrame(df['price']).resample(freq, how ='last').dropna()
    volcol  = pd.DataFrame(df['dvol']).resample(freq, how ='sum').dropna()
    datecol  = pd.DataFrame(df['date']).resample(freq, how ='last').dropna()
    oicol  = pd.DataFrame(df['openInterest']).resample(freq, how ='last').dropna()
    res =  pd.concat([opencol, highcol, lowcol, closecol, volcol, oicol, datecol], join='outer', axis =1)
    res.columns = ['open', 'high', 'low', 'close', 'volume', 'openInterest', 'date' ]
    return res

def load_hist_tick(db_table, instID, sdate, edate):
    stmt = "select instID, dtime, date, hour, min, sec, msec, price, dvol, openInterest from {dbtable} where instID='{inst}' ".format(dbtable=db_table, inst=instID)
    stmt += "and date >= '%s' " % sdate.strftime('%Y-%m-%d')
    stmt += "and date <= '%s' " % edate.strftime('%Y-%m-%d')
    stmt += "order by dtime;"
    cnx = dbaccess.connect(**dbaccess.hist_dbconfig)
    df = pd.io.sql.read_sql(stmt, cnx, index_col = 'dtime')
    return df

def load_hist_min(db_table, instID, sdate, edate):
    stmt = "select instID, exch, datetime, date, min_id, open, high, low, close, volume, openInterest from {dbtable} where instID='{inst}' ".format(dbtable=db_table, inst=instID)
    stmt += "and date >= '%s' " % sdate.strftime('%Y-%m-%d')
    stmt += "and date <= '%s' " % edate.strftime('%Y-%m-%d')
    stmt += "order by date, min_id;"
    cnx = dbaccess.connect(**dbaccess.hist_dbconfig)
    df = pd.io.sql.read_sql(stmt, cnx, index_col = 'datetime')
    return df

def conv_db_htick2min(db_table, inst_file, out_table = 'hist_fut_min', database = 'hist_data', dstep = 10):
    conf_dict = {}
    instIDs = []
    if inst_file == '':
        instIDs =  get_col_dist_values(database + '.' + db_table, 'instID',{})
        conf_dict = {'instIDs': instIDs}
        try:
            inst_file = 'instID_file.json'
            with open(inst_file, 'w') as ofile:
                json.dump(conf_dict, ofile)
        except:
            pass
    else:
        with open(inst_file, 'r') as infile:
            conf_dict = json.load(infile)
        instIDs = conf_dict['instIDs']
    dbconfig = copy.deepcopy(dbaccess.dbconfig)
    dbconfig['database']  = database
    cnx = dbaccess.connect(**dbconfig)
    for inst in instIDs:
        field_dict = {'instID': "\'"+inst+"\'"}
        datestr_list = get_col_dist_values(database + '.' + db_table, 'date', field_dict)
        mdata = pd.DataFrame()
        prod = misc.inst2product(inst)
        exch = misc.inst2exch(inst)
        num_run = (len(datestr_list)+dstep-1)/dstep
        for idx in range(num_run):
            s_idx = idx * dstep
            e_idx = min((idx + 1) *dstep - 1, len(datestr_list)-1)
            sdate = datetime.datetime.strptime(datestr_list[s_idx], "%Y-%m-%d").date()
            edate = datetime.datetime.strptime(datestr_list[e_idx], "%Y-%m-%d").date()
            df = load_hist_tick(db_table, inst, sdate, edate)
            mdf = conv_ohlc_freq(df, '1Min')
            mdf['min_id'] =  ((mdf.index.hour + 6) % 24) * 100 + mdf.index.minute
            mdf = misc.cleanup_mindata(mdf, prod)
            mdf.index.name = 'datetime'
            mdf['instID'] = inst
            mdf['exch'] = exch
            mdf = mdf.reset_index()
            mdf.set_index(['instID', 'exch', 'datetime'], inplace = True)
            mdf.to_sql(name = out_table, flavor = 'mysql', con = cnx, if_exists='append')
            cnx.commit()
            print inst, sdate, edate, len(mdf)
    cnx.close()
    return

def get_instIDs_from_file(inst_file, db_table, database = 'hist_data'):
    if inst_file == '':
        instIDs =  get_col_dist_values(database + '.' + db_table, 'instID',{})
        conf_dict = {'instIDs': instIDs}
        try:
            inst_file = 'instID_file.json'
            with open(inst_file, 'w') as ofile:
                json.dump(conf_dict, ofile)
        except:
            pass
    else:
        with open(inst_file, 'r') as infile:
            conf_dict = json.load(infile)
        instIDs = conf_dict['instIDs']
    return instIDs

def conv_db_htmin2daily(db_table, instIDs, sdate, edate, out_table = 'hist_fut_daily', database = 'hist_data'):
    dbconfig = copy.deepcopy(dbaccess.dbconfig)
    dbconfig['database'] = database
    cnx = dbaccess.connect(**dbconfig)
    for inst in instIDs:
        mdf = load_hist_min(db_table, inst, sdate, edate)
        if len(mdf) == 0:
            continue
        ddf = conv_min2daily(mdf)
        ddf.to_sql(name = out_table, flavor = 'mysql', con = cnx, if_exists='append')
        cnx.commit()
        print inst, len(ddf)
    cnx.close()
    return

def get_col_dist_values(db_table, col_name, field_dict):
    dbconfig = copy.deepcopy(dbaccess.dbconfig)
    stmt = 'select distinct({colname}) from {dbtable}'.format(colname = col_name, dbtable = db_table )
    nlen = len(field_dict.values())
    if nlen > 0:
        stmt += ' where'
        for idx, field in enumerate(field_dict.keys()):
            stmt += " {fieldname}={fvalue}".format(fieldname = field, fvalue = field_dict[field])
            if idx < nlen - 1:
                stmt += " and"
    stmt += ";"
    print stmt
    cnx = dbaccess.connect(**dbconfig)
    cursor = cnx.cursor()
    cursor.execute(stmt)
    #cnx.commit()
    keys = []
    for line in cursor:
        keys.append(str(line[0]))
    cnx.close()
    return keys

def copy_prod2hist(prod_db, hist_db, sdate, edate):
    dbconfig = copy.deepcopy(dbaccess.dbconfig)
    stmt = 'insert into {hist_db}.fut_min (instID, exch, datetime, date, min_id, open, close, high, low, volume, openInterest) '.format(hist_db = hist_db)
    stmt += 'select * from {prod_db}.fut_min where date>={sdate} and date<={edate} order by date, min_id;'.format(prod_db = prod_db, sdate = sdate.strftime('%Y%m%d'), edate = edate.strftime('%Y%m%d'));
    cnx = dbaccess.connect(**dbconfig)
    cursor = cnx.cursor()
    cursor.execute(stmt)
    cnx.commit()
    stmt = 'insert into {hist_db}.fut_daily (instID, exch, date, open, close, high, low, volume, openInterest) '.format(hist_db = hist_db)
    stmt += 'select * from {prod_db}.fut_daily where date>={sdate} and date<={edate} order by date;'.format(prod_db = prod_db, sdate = sdate.strftime('%Y%m%d'), edate = edate.strftime('%Y%m%d'))
    cursor.execute(stmt)
    cnx.commit()
    cnx.close()

def talib_get_functions_df():
    lst_info = []
    for f in talib.get_functions():
        absf = talib.abstract.Function(f)
        lst_info.append(absf.info)
    df_absf = pd.DataFrame(lst_info)
    df_absf = df_absf.set_index('name')
    return(df_absf)

def load_dates_from_csv(filename):
    with open(filename, 'rb') as f:
        reader = csv.reader(f)
        datelist = []
        for i, row in enumerate(reader):
            if i > 0:
                year = int(row[0])
                for j in range(1, len(row)):
                    try:
                        dd = int(row[j])
                        xdate = datetime.date(year, j, dd)
                        datelist.append(xdate)
                    except:
                        continue
    return datelist

def sina_fut_live(*args, **kwargs):
    lst = ",".join(args)
    url = "http://hq.sinajs.cn/list=%s" % lst
    proxy = kwargs.get('proxies', {})
    raw = urllib.urlopen(url, proxies=proxy).read()
    raw = raw.split('\n')
    result = dict()
    time_now = datetime.datetime.now()
    for i in range(len(raw) - 1):
        txt = raw[i].split(',')
        data = {
            'date': time_now.date(),
            'tick_id': misc.get_tick_id(time_now),
            'open': txt[2],
            'high': txt[3],
            'low': txt[4],
            'bidPrice1': txt[6],
            'askPrice1': txt[7],
            'price': txt[8],
            'settlement': txt[9],
            'bidVol1': txt[11],
            'askVol1': txt[12],
            'openInterest': txt[13],
            'volume': txt[14]
        }
        result[args[i]] = data
    return result


def sina_fut_hist(ticker, daily=True, proxies={}):
    # choose daily or 5 mins historical data
    if daily:
        url = 'http://stock2.finance.sina.com.cn/futures/api/json.php/IndexService.getInnerFuturesDailyKLine?symbol=%s' % ticker
    else:
        url = 'http://stock2.finance.sina.com.cn/futures/api/json.php/IndexService.getInnerFuturesMiniKLine5m?symbol=%s' % ticker
    raw = urllib.urlopen(url, proxies = proxies).read()
    result = json.loads(raw)
    return result

def process_min_id(df):
    df['min_id'] = df['datetime'].apply(lambda x: ((x.hour + 6) % 24)*100 + x.minute)
    flag = df['min_id'] >= 1000
    df.loc[flag, 'date'] = df['datetime'][flag].apply(lambda x: x.date())
    df['date'] = df['date'].fillna(method = 'bfill')
    flag = pd.isnull(df['date'])
    df.loc[flag,'date'] = df['datetime'][flag].apply(lambda x: misc.day_shift(x.date(),'1b'))
    return df

def process_trade_date(cnx, db_table = 'fut_min', col_name = 'instID'):
    stmt = 'select distinct({colname}) from {dbtable}'.format(colname=col_name, dbtable=db_table)
    cursor = cnx.cursor()
    cursor.execute(stmt)
    inst_list = []
    for line in cursor:
        inst_list.append(str(line[0]))
    for inst in inst_list:
        print "processing instID = %s" % inst
        df = dbaccess.load_min_data_to_df(cnx, db_table, inst, index_col=None)
        df['datetime'] = df['datetime'].apply(lambda x: datetime.datetime.strptime(x, "%Y-%m-%d %H:%M:%S"))
        df = process_min_id(df)
        df.to_sql('fut_min', cnx, 'sqlite', if_exists='append', index=False)


if __name__ == '__main__':
    print
