import urllib.request
import os
import sys
import tarfile
import json
import subprocess
import platform

class Zrok:
    def __init__(self, token: str, name: str = None):
        """Initialize Zrok instance with API token and optional environment name.
        
        Args:
            token (str): Zrok API token for authentication
            name (str, optional): Name/description for the zrok environment. Defaults to None.
        """
        if token.startswith('<') and token.endswith('>'):
            raise ValueError("Please provide an actual your zrok token")
        
        self.token = token
        self.name = name
        self.base_url = "https://api-v2.zrok.io/api/v2"

    def get_env(self):
        """Get overview of all zrok environments using HTTP API.

        This method uses HTTP API to retrieve environments even when zrok enable command fails.
        
        Returns:
            dict: Overview data containing environments information
            None: If the API call fails or no environments exist
        """
        req = urllib.request.Request(
            url=f"{self.base_url}/overview",
            headers={"x-token": self.token},
        )

        with urllib.request.urlopen(req) as response:
            status = response.getcode()
            data = response.read().decode('utf-8')
            data = json.loads(data) 

        if status != 200:
            print(f"Error: {status}")
            raise Exception("zrok API overview error")
        
        return data['environments']

    def find_env(self, name: str):
        overview = self.get_env()
        if overview is None:
            return None

        for item in overview:
            # Trong v2, cấu trúc 'environment' có thể chứa các trường mới như 'EnvZId'
            env = item.get("environment", {})
            if env.get("description", "").lower() == name.lower():
                return item
        return None

    def delete_environment(self, zId: str):
        """Delete a zrok environment by its ID.
        
        Args:
            zid (str): The environment ID to delete
        
        Returns:
            bool: True if the environment was successfully deleted, False otherwise
        """
        headers = {
            "x-token": self.token,
            "Accept": "*/*",
            "Content-Type": "application/zrok.v2+json"
        }
        payload = {
            "identity": zId
        }
        
        data_bytes = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(f"{self.base_url}/disable", headers=headers, data=data_bytes, method="POST")
        try:
            with urllib.request.urlopen(req) as response:
                status = response.getcode()
                if status != 200:
                    raise Exception("Failed to delete environment")
        except urllib.error.HTTPError as e:
            raise Exception(f"HTTP Error {e.code}: Failed to delete environment")

        return True

    def enable(self, name: str = None):
        """Enable zrok with the specified environment name.
        
        This method runs the 'zrok enable' command with the provided token and
        environment name. It will create a new environment if one doesn't exist.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                 If not provided, uses the name from initialization.
            
        Raises:
            RuntimeError: If enable command fails
        """
        env_name = name if name is not None else self.name
        if env_name is None:
            raise ValueError("Environment name must be provided either during initialization or when calling enable()")
        
        subprocess.run(["zrok2", "enable", self.token, "-d", env_name], check=True)

    def disable(self, name: str = None):
        env_name = name if name is not None else self.name
        try:
            # Buộc dùng zrok2 để xóa config trong ~/.zrok2
            subprocess.run(["zrok2", "disable"], check=True) 
        except subprocess.CalledProcessError:
            print(f"Warning: Local zrok2 disable failed")

        # Dọn dẹp trên web console qua API
        try:
            env = self.find_env(env_name)
            if env:
                # v2 dùng EnvZId hoặc zId để định danh
                self.delete_environment(env['environment']['zId'])
        except Exception as e:
            print(f"API cleanup warning: {e}")

    @staticmethod
    def install():
        """Install the latest version of zrok2.
        
        This method:
        1. Downloads the latest zrok2 release from GitHub
        2. Extracts the binary to /usr/local/bin/
        3. Verifies the installation
        """
        # Check if running on Windows
        if platform.system() != 'Linux':
            raise Exception("This script only works on Linux. For other operating systems, \
                            please install zrok2 manually following the instructions at https://docs.zrok.io/docs/guides/install/")

        print("Downloading latest zrok2 release")
        
        # Get latest release info
        response = urllib.request.urlopen("https://api.github.com/repos/openziti/zrok/releases/latest")
        data = json.loads(response.read())
        
        # Determine architecture
        machine = platform.machine()
        if machine == "x86_64":
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        elif machine.startswith("arm"):
            arch = "armv7"
        else:
            raise OSError(f"Unsupported architecture: {machine}")
        
        # Find the correct asset from the release
        download_url = None
        for asset in data.get("assets", []):
            url = asset["browser_download_url"]
            if f"linux_{arch}" in url and ".tar.gz" in url:
                download_url = url
                print(f"Found release: {asset['name']}")
                break
        
        if not download_url:
            print("Available releases:")
            for asset in data.get("assets", []):
                print(f"  - {asset['name']}")
            raise FileNotFoundError(f"Could not find zrok2 release for linux_{arch}")
        
        print(f"Downloading from: {download_url}")
        
        # Download zrok2
        urllib.request.urlretrieve(download_url, "zrok2.tar.gz")
        
        print("Extracting zrok2")
        with tarfile.open("zrok2.tar.gz", "r:gz") as tar:
            tar.extractall("/usr/local/bin/")
        os.remove("zrok2.tar.gz")

        # Check if zrok2 is installed correctly
        if not Zrok.is_installed():
            raise RuntimeError("Failed to verify zrok2 installation")
        
        print("Successfully installed zrok2")

    @staticmethod
    def is_installed():
        """Check if zrok is installed and accessible.
        
        Returns:
            bool: True if zrok is installed and can be executed, False otherwise
        """
        try:
            subprocess.run(["zrok2", "version"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def is_enabled() -> bool:
        """Check if zrok is enabled.
        
        Returns:
            bool: True if zrok is enabled (Account Token and Ziti Identity are set), False otherwise
        """
        try:
            result = subprocess.run(
                ["zrok2", "status"],
                capture_output=True,
                text=True,
                check=True
            )
            # Check if both Account Token and Ziti Identity are set
            return "Account Token  <<SET>>" in result.stdout and "Ziti Identity  <<SET>>" in result.stdout
        except subprocess.CalledProcessError:
            return False
        except FileNotFoundError:
            return False

  