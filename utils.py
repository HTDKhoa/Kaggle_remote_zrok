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
        self.base_url = "https://api-v1.zrok.io/api/v1"

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
        """Find a specific environment by its name.
        
        Args:
            name (str): Name/description of the environment to find (case-insensitive)
        
        Returns:
            dict: Environment information if found
            None: If no environment matches the given name
        """
        overview = self.get_env()
        if overview is None:
            return None

        for item in overview:
            env = item["environment"]
            if env["description"].lower() == name.lower():
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
            "Content-Type": "application/zrok.v1+json"
        }
        payload = {
            "identity": zId
        }
        
        data_bytes = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(f"{self.base_url}/disable", headers=headers, data=data_bytes, method="POST")
        with urllib.request.urlopen(req) as response:
            status = response.getcode()

        if status != 200:
            raise Exception("Failed to delete environment")

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
        
        subprocess.run(["zrok", "enable", self.token, "-d", env_name], check=True)

    def disable(self, name: str = None):
        """Disable zrok.
        
        This function executes the zrok disable command to delete the environment stored in the local file ~/.zrok/environment.json,
        and additionally removes any environments that could not be deleted through HTTP communication.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                If not provided, uses the name from initialization.
        """
        env_name = name if name is not None else self.name

        # Delete the ~/.zrok/environment.json file
        try:
            subprocess.run(["zrok", "disable"], check=True)
        except Exception as e:
            print(e)
            print("zrok already disable")

        # Delete environment via HTTP communication even if zrok is not enabled
        env = self.find_env(env_name)
        if env is not None:
            self.delete_environment(env['environment']['zId'])

    @staticmethod
    def install(version: str = "1.1.11"):
        """Install zrok, optionally specifying a version.
        
        This method:
        1. Downloads zrok release from GitHub (latest or specific version)
        2. Extracts the binary to /usr/local/bin/
        3. Verifies the installation
        
        Args:
            version (str, optional): Specific version to install (e.g., "1.1.11").
                                   If not provided, installs the latest version.
        """

        version_str = version if version else "latest"
        print(f"Downloading zrok {version_str} release")
        # Get release info
        if version:
            release_url = f"https://api.github.com/repos/openziti/zrok/releases/tags/v{version}"
        else:
            release_url = "https://api.github.com/repos/openziti/zrok/releases/latest"
        response = urllib.request.urlopen(release_url)
        data = json.loads(response.read())
        
        # Determine the correct download URL based on OS
        download_url = None
        filename = None
        system = platform.system()
        
        if system == 'Linux':
            for asset in data["assets"]:
                url = asset["browser_download_url"]
                if "linux" in url.lower() and "amd64" in url.lower() and url.endswith(".tar.gz"):
                    download_url = url
                    filename = "zrok.tar.gz"
                    break
        elif system == 'Windows':
            for asset in data["assets"]:
                url = asset["browser_download_url"]
                if "windows" in url.lower() and "amd64" in url.lower() and url.endswith(".tar.gz"):
                    download_url = url
                    filename = "zrok.tar.gz"
                    break
        elif system == 'Darwin':  # macOS
            for asset in data["assets"]:
                url = asset["browser_download_url"]
                if "darwin" in url.lower() and "amd64" in url.lower() and url.endswith(".tar.gz"):
                    download_url = url
                    filename = "zrok.tar.gz"
                    break
        else:
            raise Exception(f"Unsupported operating system: {system}. Please install zrok manually from https://docs.zrok.io/docs/guides/install/")
        
        if not download_url:
            raise FileNotFoundError(f"Could not find zrok download URL for {system}")
        
        # Download zrok
        urllib.request.urlretrieve(download_url, filename)
        
        print("Extracting zrok")
        
        if system == 'Linux' or system == 'Darwin':
            with tarfile.open(filename, "r:gz") as tar:
                tar.extractall("/usr/local/bin/")
            os.remove(filename)
        elif system == 'Windows':
            # Extract to user's local AppData or a directory in PATH
            install_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'zrok')
            os.makedirs(install_dir, exist_ok=True)
            
            with tarfile.open(filename, "r:gz") as tar:
                tar.extractall(install_dir)
            os.remove(filename)
            
            # Add to PATH for current session
            if install_dir not in os.environ.get('PATH', ''):
                os.environ['PATH'] = install_dir + os.pathsep + os.environ['PATH']
                print(f"\nzrok extracted to: {install_dir}")
                print(f"Added to PATH for this session.")
                print(f"For permanent PATH addition, run:")
                print(f"   setx PATH \"%PATH%;{install_dir}\"")
                print("Then restart your terminal.")

        # Check if zrok is installed correctly
        if not Zrok.is_installed():
            if system == 'Windows':
                raise RuntimeError("Failed to verify zrok installation. Please restart your terminal after running setx command.")
            else:
                raise RuntimeError("Failed to verify zrok installation")
        
        print("Successfully installed zrok")

    @staticmethod
    def is_installed():
        """Check if zrok is installed and accessible.
        
        Returns:
            bool: True if zrok is installed and can be executed, False otherwise
        """
        try:
            subprocess.run(["zrok", "version"], check=True)
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
                ["zrok", "status"],
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

  