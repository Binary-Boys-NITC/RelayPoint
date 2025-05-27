# Python Virtual Environment Setup

## Prerequisites
- Python 3.x installed on your system
- pip (Python package installer)

## Setting up Virtual Environment

1. Open terminal/command prompt in your project directory

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. Verify the virtual environment is activated:
   - You should see `(venv)` at the beginning of your command prompt
   - Check Python location:
     ```bash
     which python  # macOS/Linux
     where python  # Windows
     ```

5. Install required packages:
   ```bash
   pip install -r requirements.txt  # if you have a requirements.txt file
   ```

6. Deactivate the virtual environment when done:
   ```bash
   deactivate
   ```

