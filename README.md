# Chikara

> [!NOTE]
> Older versions of Qlute before or at 2024.11.10 will experience problems connecting to the server as those are depreciated.

📖 **Full server manual (setup, configuration, features, API, operations): [docs/MANUAL.md](docs/MANUAL.md)**

## Installation

Tested on Debian, Ubuntu 22.04

### Step 1: install Django, gunicorn, nginx, venv, git, mariadb

```
sudo apt install python3.10-venv gunicorn nginx git mariadb-server
git clone https://github.com/Jinkkuu/Chikara && cd Chikara 
python3 -m venv .venv # Creates the virtual environment
source .venv/bin/activate # activates the virtual environment
pip3 install django # installs django into a virtual environment
```

### Step 2: install Django, gunicorn, nginx, venv, git, mariadb




## Licence

*Chikara*'s code are licensed under the [MIT licence](https://opensource.org/licenses/MIT). Please see [the licence file](LICENCE) for more information. [tl;dr](https://tldrlegal.com/license/mit-license) you can do whatever you want as long as you include the original copyright and license notice in any copy of the software/source.