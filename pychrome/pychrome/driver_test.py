from pychrome import Driver
from pychrome.test_utils import new_browser, TEST_ADDR


def test_get_endpoints():
    driver = Driver(TEST_ADDR)
    endpoints = driver.get_endpoints()

    for ep in endpoints:
        print(ep)

    for conn in driver.connections('.*'):
        print(conn)
