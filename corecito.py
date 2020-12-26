#!/usr/bin/env python3
import asyncio
import time
import logging
import yaml
import sys
from os.path import exists
import cryptocom.exchange as cro
from cryptocom.exchange.structs import Pair
from cryptocom.exchange.structs import PrivateTrade

async def main():
  config = get_config()
  logger = setupLogger('logfile.log')
  exchange = cro.Exchange()
  account = cro.Account(api_key=config['cryptocom_api_key'], api_secret=config['cryptocom_api_secret'])
  core_number = config['core_number']
  pair = eval('cro.pairs.' + config['trading_pair'])
  base_currency = config['base_currency']
  cro_coin_base_currency = eval('cro.coins.' + config['base_currency'])
  core_number_currency = config['core_number_currency']
  cro_coin_core_number_currency = eval('cro.coins.' + config['core_number_currency'])
  iteration = 0

  while True:
    iteration += 1
    print(f'------------ Iteration {iteration} ------------')
    # Get BTC/ETH ticker info
    tickers = await exchange.get_tickers()
    ticker = tickers[pair]
    buy_price = ticker.buy_price
    sell_price = ticker.sell_price
    high = ticker.high
    low = ticker.low
    logger.info(f'\nMarket {pair.name}\nbuy price: {buy_price} - sell price: {sell_price} <> low: {low} - high: {high}\n')

    # EXAMPLE ticker = MarketTicker(pair=Pair(name='ETH_BTC'),
    # buy_price=0.027638, sell_price=0.027641, trade_price=0.027641,
    # time=1608466157, volume=10596.948,
    # high=0.028549, low=0.027439, change=-0.001)

    # Get my BTC balance
    balances = await account.get_balance()
    base_currency_balance = balances[cro_coin_base_currency]
    base_currency_available = base_currency_balance.available
    # EXAMPLE BTC_balance:Balance(total=0.04140678, available=3.243e-05, in_orders=0.04137435, in_stake=0, coin=Coin(name='BTC'))

    # Get my ETH balance
    core_number_currency_balance = balances[cro_coin_core_number_currency]

    logger.info(f'Balances\n(Base) {base_currency} balance:{base_currency_balance} \n(Core) {core_number_currency} balance:{core_number_currency_balance}\n')

    ###########################
    # Core Number Adjustments #
    ###########################
    deviated_core_number = base_currency_available / buy_price
    logger.info(f'Core number adjustments')
    logger.info(f'Core number: {core_number} {core_number_currency}')
    logger.info(f'Deviated Core number:{deviated_core_number:.6f} {core_number_currency}')
    excess = round(deviated_core_number - core_number, config['max_decimals_buy'])
    increase_percentage = excess * 100 / core_number
    missing = round(core_number - deviated_core_number, config['max_decimals_sell'])
    decrease_percentage = missing * 100 / core_number

    if coreNumberExploded(core_number, deviated_core_number, config['max_core_number_increase_percentage']):
      logger.info(f'> Exploded {increase_percentage:.2f}%\nConsider updating CoreNumber to {deviated_core_number:.6f}')

    elif coreNumberIncreased(core_number, deviated_core_number, config['min_core_number_increase_percentage'], config['max_core_number_increase_percentage']):
      logger.info(f'Increased {increase_percentage:.2f}% - excess of {excess:.6f} {core_number_currency} denominated in {base_currency}')
      tx_result = round(excess * buy_price, config['max_decimals_buy'])
      logger.info(f'\n\n>>> Selling: {tx_result:.6f} {base_currency} at {buy_price} to park an excess of {excess:.6f} {core_number_currency}\n')
      # Sell excess BTC => Market Sell for ETH_BTC is denominated in BTC!!!
      if (not config['safe_mode_on']):
        await account.buy_market(pair, tx_result)

    elif coreNumberDecreased(core_number, deviated_core_number, config['min_core_number_decrease_percentage'], config['max_core_number_decrease_percentage']):
      logger.info(f'Decreased {decrease_percentage:.2f}% - missing {missing:.6f} {core_number_currency} denominated in {base_currency}')
      tx_result = missing * sell_price
      logger.info(f'\n\n>>> Buying: {tx_result:.6f} {base_currency} at {buy_price} taking {missing:.6f} {core_number_currency} from reserves\n')
      # Buy missing BTC => Sell ETH
      if (not config['safe_mode_on']):
        await account.sell_market(pair, missing)

    elif coreNumberPlummeted(core_number, deviated_core_number, config['max_core_number_decrease_percentage']):
      logger.info(f'> Plummeted {decrease_percentage:.2f}%\nConsider updating CoreNumber to {deviated_core_number:.6f}')

    else:
      logger.info(f'> Price is rock-solid stable ({increase_percentage:.2f}%)')

    # Update balances after adjusting to core number
    balances = await account.get_balance()
    logger.info(f'Final {base_currency} available:{balances[cro_coin_base_currency].available} - {core_number_currency} available:{balances[cro_coin_core_number_currency].available}')

    # Loop end
    print(f'------------ Iteration {iteration} ------------\n')
    if config['test_mode_on']:
      await asyncio.sleep(1)
      break
    else:
      # Wait given seconds until next poll
      logger.info("Waiting for next iteration... ({} seconds)\n\n\n".format(config['seconds_between_iterations']))
      await asyncio.sleep(config['seconds_between_iterations'])



def get_config():
  config_path = "config/default_config.yaml"
  if exists("config/user_config.yaml"):
    config_path = "config/user_config.yaml"
    print('\n\nDetected user configuration...\n')
  else:
    print('Loading default configuration...')
  config_file = open(config_path)
  data = yaml.load(config_file, Loader=yaml.FullLoader)
  config_file.close()
  check_config(data)
  return data

def check_config(data):
  try:
    eval('cro.pairs.' + data['trading_pair'])
  except AttributeError:
    print('Trading pair "{}" does not exist (check your config_file)'.format(data['trading_pair']))
    sys.exit(1)
  try:
    eval('cro.coins.' + data['core_number_currency'])
  except AttributeError:
    print('Currency "{}" does not exist (check your config_file)'.format(data['core_number_currency']))
    sys.exit(1)
  try:
    eval('cro.coins.' + data['base_currency'])
  except AttributeError:
    print('Currency "{}" does not exist (check your config_file)'.format(data['base_currency']))
    sys.exit(1)


def coreNumberIncreased(core_number, deviated_core_number, min_core_number_increase_percentage, max_core_number_increase_percentage):
  min_core_number_increase = core_number * (1 + (min_core_number_increase_percentage/100))
  max_core_number_increase = core_number * (1 + (max_core_number_increase_percentage/100))
  return deviated_core_number >= min_core_number_increase and deviated_core_number <= max_core_number_increase

def coreNumberExploded(core_number, deviated_core_number, max_core_number_increase_percentage):
  max_core_number_increase = core_number * (1 + (max_core_number_increase_percentage/100))
  return deviated_core_number > max_core_number_increase

def coreNumberDecreased(core_number, deviated_core_number, min_core_number_decrease_percentage, max_core_number_decrease_percentage):
  min_core_number_decrease = core_number * (1 - (min_core_number_decrease_percentage/100))
  max_core_number_decrease = core_number * (1 - (max_core_number_decrease_percentage/100))
  return deviated_core_number <= min_core_number_decrease and deviated_core_number >= max_core_number_decrease

def coreNumberPlummeted(core_number, deviated_core_number, max_core_number_decrease_percentage):
  max_core_number_decrease = core_number * (1 - (max_core_number_decrease_percentage/100))
  return deviated_core_number < max_core_number_decrease

def setupLogger(log_filename):
  logger = logging.getLogger('CN')

  file_log_handler = logging.FileHandler(log_filename)
  logger.addHandler(file_log_handler)

  stderr_log_handler = logging.StreamHandler()
  logger.addHandler(stderr_log_handler)

  # nice output format
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  file_log_handler.setFormatter(formatter)
  stderr_log_handler.setFormatter(formatter)

  logger.setLevel('DEBUG')
  return logger



loop = asyncio.get_event_loop()
try:
  loop.run_until_complete(main())
except KeyboardInterrupt:
  pass
finally:
  print("Stopping Corecito...")
  loop.close()
