![rolm_3_Banner](graphics/rolm_3.png)

# Discord-Role-Manager (Rolm)
[![Pipeline](https://img.shields.io/github/actions/workflow/status/Geoffery10/Discord-Role-Manager/test.yml)](https://github.com/Geoffery10/Discord-Role-Manager/actions/workflows/test.yml) ![Coveralls](https://img.shields.io/coverallsCoverage/github/Geoffery10/Discord-Role-Manager)
![GitHub contributors](https://img.shields.io/github/contributors/Geoffery10/Discord-Role-Manager)
![GitHub top language](https://img.shields.io/github/languages/top/Geoffery10/Discord-Role-Manager)

This is a role manager for my personal Discord servers
## Table of Contents
* [Getting Started](#getting-started)
* [Built With](#built-with)
* [Contributing](#contributing)  
* [Authors](#authors)
* [License](#license)

## Getting Started
1. Clone or download the repository.
2. Ensure you have Python 3.10+ installed.
3. Install the project dependencies with `pdm install`.
4. (Optional) Install development dependencies for testing: `pdm install -d`.
5. Configure `roles.json` with the roles you want to manage and their associated emojis.
6. To run the bot, execute `pdm run` (or `run.bat` on Windows).

## Running Tests
After installing the development dependencies, you can run the test suite with:
```bash
pdm test
```
or directly with pytest:
```bash
pytest
```

#### Reasons your install failed: 

* Missing pdm (Install pdm using `pip install pdm`)

## Contributing

Interested in contributing? Feel free to reach out to me on my discord! geoffery10 <img align="center" width="18" height="18" src="https://cdn3.iconfinder.com/data/icons/popular-services-brands-vol-2/512/discord-128.png">

## Authors
* Geoffery Powell - [Geoffery10](https://github.com/Geoffery10)

## License

This project is licensed under the **GNU General Public License v3.0** – see the [LICENSE](LICENSE) file for details.
