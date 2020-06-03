from selenium.webdriver.remote.command import Command
from selenium.webdriver.remote.webdriver import WebDriver


class RemoteWebDriver(WebDriver):
    def start_session(self, desired_capabilities, browser_profile=None):
        response = self.execute(Command.GET_ALL_SESSIONS)
        print(response)
        assert isinstance(response['value'], list)
        if len(response['value']) == 0:
            super().start_session(desired_capabilities=desired_capabilities, browser_profile=browser_profile)
        else:
            print('#')
            self.session_id = response['value'][0]['id']
            self.capabilities = response['value'][0]['capabilities']
            # Quick check to see if we have a W3C Compliant browser
            self.w3c = response.get('status') is None