import datetime
import time
import os
import pandas as pd
from dateutil.rrule import rrule, DAILY, MONTHLY
from django.core.exceptions import ObjectDoesNotExist
from sqlalchemy import create_engine
import json5

"""""
資料庫設定
"""""
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('/crawlers', '')
with open(os.path.join(BASE_DIR, "config.json"), 'r', encoding='utf8') as file:
    CONFIG_DATA = json5.load(file)
connect_info = 'mysql+pymysql://{}:{}@{}:{}/{}?charset=utf8'.format(CONFIG_DATA['DBACCOUNT'], CONFIG_DATA['DBPASSWORD'],
                                                                    CONFIG_DATA['DBHOST'], CONFIG_DATA['DBPORT'],
                                                                    CONFIG_DATA['DBNAME'])
engine = create_engine(connect_info)

"""""
日單位集合產生器
"""""


def date_range(start_date, end_date):
    # Todo
    return [dt.date() for dt in rrule(DAILY, dtstart=start_date, until=end_date)]


"""""
月單位集合產生器
"""""


def month_range(start_date, end_date):
    return [dt.date() for dt in rrule(MONTHLY, dtstart=start_date, until=end_date)]


"""""
季單位集合產生器
"""""


def season_range(start_date, end_date):
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()

    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()

    ret = []
    for year in range(start_date.year - 1, end_date.year + 1):
        ret += [datetime.date(year, 5, 15),
                datetime.date(year, 8, 14),
                datetime.date(year, 11, 14),
                datetime.date(year + 1, 3, 31)]
    ret = [r for r in ret if start_date < r < end_date]

    return ret


"""""
Table存在判斷
"""""


def table_exist(conn, table):
    return list(conn.execute(
        "select count(*) from information_schema.tables where TABLE_NAME=" + "'" + table + "'"))[0][0] == 1


"""""
Table最新資料日
"""""


def table_latest_date(conn, table):
    try:
        cursor = list(conn.execute('SELECT date FROM ' + table + ' ORDER BY date DESC LIMIT 1;'))
        return cursor[0][0]
    except IndexError:
        return print("No Data")


"""""
Table最早資料日
"""""


def table_earliest_date(conn, table):
    try:
        cursor = list(conn.execute('SELECT date FROM ' + table + ' ORDER BY date ASC LIMIT 1;'))
        return cursor[0][0]
    except IndexError:
        return print("No Data")


"""""
Table日期存在判斷
"""""


def in_date_list(conn, model_name, check_date):
    table = model_name._meta.db_table
    cursor = list(conn.execute("SELECT date FROM " + table + " where date ='" + check_date + "'"))
    try:
        if len(cursor) > 0:
            return True
        else:
            return False
    except IndexError:
        print("No Data in table,start to init import table. ")
        return False


"""""
Dataframe匯入DB,適用時間序列資料
"""""


def add_to_sql(model_name, df):
    bulk_update_data = []
    bulk_create_data = []
    columns_list = model_name._meta.fields[1:]

    # if data_date isn't in table,process bulk_create
    if 'date' in [field.name for field in columns_list]:
        data_date = df['date'].iloc[0].strftime('%Y-%m-%d')
        check_date = in_date_list(engine, model_name, data_date)
    else:
        check_date = True

    if check_date is False:
        # Change CSV to iterrow
        for index, item in df.iterrows():
            # Use bulk_update to update obj,PS:must include prime_key column
            try:
                obj_create_data = dict((field.name, item[field.name]) for field in columns_list)
                obj_create = model_name(**obj_create_data)
                bulk_create_data.append(obj_create)
                print(f"create{' '}{' '}Stock_id:{item['stock_id']}")

            except Exception as e:
                print(f"error{' '}{e}{' '}Stock_id:{item['stock_id']}")
                pass

    else:
        # Change CSV to iterrow
        for index, item in df.iterrows():

            # Use bulk_update to update obj,PS:must include primekey column
            try:
                if 'date' in [field.name for field in columns_list]:
                    obj_check = model_name.objects.get(stock_id=item['stock_id'], date=item['date'])
                else:
                    obj_check = model_name.objects.get(stock_id=item['stock_id'])

                attribute_data = [field.name for field in columns_list]
                update_data = [item[field.name] for field in columns_list]

                for attribute, update_value in zip(attribute_data, update_data):
                    setattr(obj_check, attribute, update_value)

                bulk_update_data.append(obj_check)
                print(f"update{' '}{' '}Stock_id:{item['stock_id']}")

            # Use dict to bulk_create obj when get nothing ,process incomplete data
            except ObjectDoesNotExist:
                obj_create_data = dict((field.name, item[field.name]) for field in columns_list)
                obj_create = model_name(**obj_create_data)
                bulk_create_data.append(obj_create)
                print(f"create{' '}{' '}Stock_id:{item['stock_id']}")

            except Exception as e:
                print(f"error{' '}{e}{' '}Stock_id:{item['stock_id']}")
                pass

    # Process bulk
    model_name.objects.bulk_create(bulk_create_data, batch_size=1000)
    if 'date' in [field.name for field in columns_list]:
        print_date = df['date'].values[0]
    else:
        print_date = df['update_time'].values[0]
    print(f"Finish{' '}{model_name}{'date'}{':'}{print_date}{' '}{'bulk_create'}{':'}{len(bulk_create_data)}")
    update_fields_area = [field.name for field in model_name._meta.fields if field.name != 'id']
    model_name.objects.bulk_update(bulk_update_data, update_fields_area, batch_size=1000)
    print(f"Finish{' '}{model_name}{'date'}{':'}{print_date}{' '}{'bulk_update'}{':'}{len(bulk_update_data)}")


"""""
爬蟲執行物件,適用時間序列資料
"""""


class CrawlerProcess:

    def __init__(self, crawl_class, crawl_method, model_name, range_date):
        self.crawl_class = crawl_class
        self.crawl_method = crawl_method
        self.model_name = model_name
        self.table_latest_date = table_latest_date(engine, self.model_name._meta.db_table)
        self.range_date = range_date

    def __repr__(self):
        return str(self.model_name._meta.db_table) + ' ' + "table_latest_date:" + str(self.table_latest_date)

    def crawl_process(self, date_list: list):

        for d in date_list:
            df = getattr(self.crawl_class(d), self.crawl_method)()
            try:
                ret = df.drop_duplicates(['stock_id', 'date'], keep='last')
                add_to_sql(self.model_name, ret)
                print(f'Finish {d} Data')

            # holiday is blank
            except AttributeError:
                print(f'fail, check if {d} is a holiday')
            time.sleep(12)

    # 指定區間，主要為初始化table和測試用
    def specified_date_crawl(self, start_date: str, end_date: str):

        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")

        try:
            if (start_date - end_date).days <= 0:
                if self.range_date == 'date_range':
                    date_list = date_range(start_date, end_date)[1:]
                elif self.range_date == 'month_range':
                    end_date = end_date + datetime.timedelta(days=15)
                    date_list = month_range(start_date, end_date)
                    date_list = date_list
                else:
                    print(f"Finish Update Work")
                    return None

                self.crawl_process(date_list)
            else:
                print(f"The start_date > your end_date,please modify your start_date <={end_date} .")

        except ValueError:
            print('Error:last_day form is %Y-%m-%d or df include NaTType,it does not support utcoffset ')
            return None

    # 進度判斷
    def working_process(self):
        recent = datetime.datetime.now()
        try:
            day_num = (recent - self.table_latest_date).days
            if self.range_date == 'date_range':
                if day_num > 0:
                    return 0
                elif day_num == 0:
                    return 1
                else:
                    return 2

            elif self.range_date == 'month_range':
                return 0
        except TypeError:
            print(f"Please use specified_date_crawl to Init Table ")
            return -1

    # 自動爬取結尾後日期的資料
    def auto_update_crawl(self, last_day='Now'):

        try:
            if last_day == 'Now':
                end_date = datetime.datetime.now()
            else:
                end_date = datetime.datetime.strptime(last_day, "%Y-%m-%d")

            if self.working_process() == 0:
                start_date = self.table_latest_date
                if self.range_date == 'date_range':
                    # [1:] avoid same index,let program be faster
                    date_list = date_range(start_date, end_date)[1:]
                elif self.range_date == 'month_range':
                    if end_date.day > 15:
                        print(f"day > 15,Finish Update Work")
                        return None
                    # add 15 day to append month range,because deadline is 10,if the day is 1-9,it need update
                    end_date = end_date + datetime.timedelta(days=15)
                    date_list = month_range(start_date, end_date)
                else:
                    date_list = season_range(start_date, end_date)
                self.crawl_process(date_list)

            elif self.working_process() == 1:
                print(f"Finish Update Work")
                return None
            elif self.working_process() == -1:
                print(f"Please use specified_date_crawl to Init Table ")
                return None
            else:
                print(f"The table_latest_date > your setting date,please modify your setting date >{last_day} .")
                return None

        except ValueError:
            print('Error:last_day form is %Y-%m-%d,please modify. ')
            return None