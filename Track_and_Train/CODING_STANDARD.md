# Train & Track Control System
# Coding Standards

**Author: Wunmi Salami**

**ECE 1140: Systems and Project Engineering**

**December 11, 2025**

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Contributing](#2-contributing)
   - 2.1 [Project Structure](#21-project-structure)
   - 2.2 [Pull Requests](#22-pull-requests)
   - 2.3 [Testing Standards](#23-testing-standards)
3. [Source File Basics](#3-source-file-basics)
   - 3.1 [File Name](#31-file-name)
   - 3.2 [File Encoding](#32-file-encoding)
4. [Formatting](#4-formatting)
   - 4.1 [Indentation & Brackets](#41-indentation--brackets)
   - 4.2 [Maximum Line Length](#42-maximum-line-length)
   - 4.3 [Imports](#43-imports)
   - 4.4 [Blank Lines](#44-blank-lines)
   - 4.5 [String Quotes](#45-string-quotes)
   - 4.6 [Whitespace Rules](#46-whitespace-rules)
5. [Comments](#5-comments)
   - 5.1 [Block Comments](#51-block-comments)
   - 5.2 [Inline Comments](#52-inline-comments)
   - 5.3 [Docstrings](#53-docstrings)
6. [Naming Conventions](#6-naming-conventions)
   - 6.1 [Naming Styles](#61-naming-styles)
   - 6.2 [Class Names](#62-class-names)
   - 6.3 [Function and Variable Names](#63-function-and-variable-names)
   - 6.4 [Properties and Attributes](#64-properties-and-attributes)
   - 6.5 [Method Names](#65-method-names)
   - 6.6 [Constant Names](#66-constant-names)
7. [Exception Handling](#7-exception-handling)
8. [Recommendations](#8-recommendations)

---

## 1. Introduction

This document defines the coding standards and practices for writing Python code in the Train & Track Control System project. Following these standards ensures code consistency, maintainability, and quality across all modules.

**Primary Reference:** [PEP 8 - Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/)

This document serves as a quick reference for project-specific conventions and requirements.

---

## 2. Contributing

### 2.1 Project Structure

The project follows this structure:

```
Track_and_Train/
├── Combined_ui.py          # Main launcher
├── Track_Model/            # Track infrastructure module
├── Train_Model/            # Train simulation module
├── logs/                   # System logs
├── track_io.json          # Inter-module communication
├── ctc_data.json          # Control data
└── track_model_Train_Model.json
```

**Branch Strategy:**
- `main` branch is protected
- Create feature branches: `feature/description` or `fix/description`
- All development on feature branches, merge via pull request

### 2.2 Pull Requests

**Before Creating PR:**
1. Ensure all tests pass
2. Run code formatter (if available)
3. Check for unused imports
4. Verify no debug print statements remain

**PR Requirements:**
- Clear description of changes
- Link to related issues (if applicable)
- At least one self-review
- All tests passing
- No merge conflicts

**After Approval:**
- Squash and merge to keep linear history
- Delete feature branch after merge

### 2.3 Testing Standards

**Unit Tests:**
- Write tests for all new functions and classes
- Cover edge cases and error conditions
- Use descriptive test function names

**Integration Tests:**
- Test inter-module communication
- Verify JSON file read/write operations
- Test complete user workflows

**Test Organization:**
- Test files mirror source structure
- One test file per module file
- Group related tests in classes

---

## 3. Source File Basics

### 3.1 File Name

**Python Files:**
- Use lowercase letters
- Separate words with underscores
- Match primary class/function purpose

**Examples:**
```
✓ train_model.py
✓ track_controller.py
✓ train_data_sync.py

✗ TrainModel.py
✗ trackController.py
✗ tm.py
```

**Exceptions:**
- `Combined_ui.py` (legacy naming)
- `README.md`
- `LICENSE`

### 3.2 File Encoding

All source files must be encoded in **UTF-8**.

Verify encoding in your editor settings before saving files.

---

## 4. Formatting

### 4.1 Indentation & Brackets

**Use 4 spaces per indentation level. Never use tabs.**

Configure your editor to convert tabs to 4 spaces.

**Opening brackets on same line:**
```python
# Good
def calculate_speed(velocity, acceleration, time):
    return velocity + acceleration * time

# Bad
def calculate_speed(velocity, acceleration, time)
:
    return velocity + acceleration * time
```

**Continuation lines:**
```python
# Good - Aligned with opening delimiter
result = long_function_name(
    argument_one, argument_two,
    argument_three, argument_four
)

# Good - Hanging indent
result = long_function_name(
    argument_one,
    argument_two,
    argument_three
)

# Bad
result = long_function_name(argument_one, argument_two,
    argument_three, argument_four)
```

**Use brackets for implicit line joining:**
```python
# Good
message = (
    "This is a very long message that "
    "spans multiple lines for readability"
)

# Avoid backslashes
message = "This is a very long message that " \
          "spans multiple lines"
```

### 4.2 Maximum Line Length

**Limit all lines to maximum 88 characters.**

This is the Black formatter standard and provides good readability.

**Breaking long lines:**
```python
# Good
with open('/path/to/file.json', 'r') as f:
    data = json.load(f)

# Good - use implicit continuation
train_data = {
    "speed": current_speed,
    "position": current_position,
    "authority": remaining_authority
}

# Break before binary operators
total = (
    first_value
    + second_value
    - third_value
)
```

### 4.3 Imports

**Always at top of file.**

**Import order:**
1. Standard library imports
2. Third-party imports
3. Local application imports

**Separate groups with blank line:**
```python
# Standard library
import os
import sys
import json
from datetime import datetime

# Third-party
import pandas as pd
from tkinter import ttk

# Local
from train_model import TrainModel
from track_controller import TrackController
```

**One import per line for standard imports:**
```python
# Good
import os
import sys

# Bad
import os, sys
```

**Multiple items from same module allowed:**
```python
# Good
from datetime import datetime, timedelta
```

**Avoid wildcard imports:**
```python
# Bad
from train_model import *

# Good
from train_model import TrainModel, SpeedController
```

### 4.4 Blank Lines

**Two blank lines:**
- Around top-level functions
- Around top-level classes

**One blank line:**
- Between method definitions inside a class
- To separate logical sections within functions (sparingly)

**Example:**
```python
import sys


class TrainModel:
    def __init__(self):
        self.speed = 0

    def update_speed(self, new_speed):
        self.speed = new_speed


class TrackModel:
    def __init__(self):
        self.blocks = []


def standalone_function():
    return True
```

### 4.5 String Quotes

**Use double quotes exclusively.**

```python
# Good
message = "Hello, World"
station = "SHADYSIDE"

# Bad
message = 'Hello, World'
station = 'SHADYSIDE'
```

**Exception: Strings containing double quotes:**
```python
# Acceptable
message = 'He said "Hello"'

# Or use escaping
message = "He said \"Hello\""
```

**Triple quotes for docstrings:**
```python
"""This is a docstring."""
```

### 4.6 Whitespace Rules

#### 4.6.1 Avoid Extra Whitespace

**Inside parentheses, brackets, or braces:**
```python
# Good
spam(ham[1], {eggs: 2})

# Bad
spam( ham[ 1 ], { eggs: 2 } )
```

**Before commas, semicolons, or colons:**
```python
# Good
if x == 4:
    print(x, y)

# Bad
if x == 4 :
    print(x , y)
```

**Before function call parentheses:**
```python
# Good
spam(1)

# Bad
spam (1)
```

#### 4.6.2 Use Single Spaces Around

**Assignment operators:**
```python
x = 1
y += 2
z -= 3
```

**Comparison operators:**
```python
if x == 4:
if x < 5:
if x >= y:
```

**Boolean operators:**
```python
if x and y:
if not z:
```

#### 4.6.3 Special Cases

**No spaces around = in keyword arguments:**
```python
# Good
def func(arg1, arg2=None):
    pass

func(arg1=value, arg2=10)

# Bad
def func(arg1, arg2 = None):
    pass
```

**Spaces around = with type annotations:**
```python
# Good
def func(arg: str = "default"):
    pass

# Bad
def func(arg: str="default"):
    pass
```

---

## 5. Comments

Comments that contradict code are worse than no comments. **Always keep comments up-to-date.**

Comments should be complete sentences. First word capitalized unless it's an identifier beginning with lowercase.

### 5.1 Block Comments

Block comments apply to code that follows them and are indented to the same level.

Each line starts with `#` and a single space.

Paragraphs separated by line containing single `#`.

**Example:**
```python
# Calculate braking distance based on current velocity and
# maximum deceleration rate. This ensures the train stops
# before exceeding authority.
#
# Formula: d = v² / (2 * a)
braking_distance = (velocity ** 2) / (2 * max_deceleration)
```

### 5.2 Inline Comments

Use sparingly. Separate from code by at least two spaces.

```python
# Good
authority -= 1  # Decrement remaining blocks

# Bad - obvious comment
x = x + 1  # Increment x

# Bad - too close
authority -= 1# Decrement blocks
```

### 5.3 Docstrings

Write docstrings for all **public modules, functions, classes, and methods.**

**One-line docstrings:**
```python
def get_speed():
    """Return current train speed in mph."""
    return self.speed
```

**Multi-line docstrings:**
```python
def calculate_position(velocity, time, acceleration):
    """
    Calculate new position using kinematic equations.
    
    Args:
        velocity (float): Current velocity in m/s
        time (float): Time interval in seconds
        acceleration (float): Acceleration in m/s²
        
    Returns:
        float: New position in meters
    """
    return velocity * time + 0.5 * acceleration * (time ** 2)
```

**Class docstrings:**
```python
class TrainModel:
    """
    Simulates train physics and behavior.
    
    The TrainModel handles acceleration, braking, position updates,
    and communication with Track Model and Train Controller.
    
    Attributes:
        speed (float): Current speed in mph
        position (float): Current position in yards
        authority (int): Remaining authority in blocks
    """
    
    def __init__(self):
        pass
```

---

## 6. Naming Conventions

### 6.1 Naming Styles

Common naming styles:
- `b` (single lowercase letter)
- `B` (single uppercase letter)
- `lowercase`
- `lower_case_with_underscores` (snake_case)
- `UPPERCASE`
- `UPPER_CASE_WITH_UNDERSCORES` (UPPER_SNAKE_CASE)
- `CapitalizedWords` (PascalCase, CamelCase)
- `mixedCase` (differs from CamelCase by initial lowercase)

**Acronyms in CamelCase:**
Capitalize all letters: `HTTPServerError` not `HttpServerError`

### 6.2 Class Names

Use **PascalCase** (CapWords).

```python
# Good
class TrainModel:
class SpeedController:
class DynamicBlockManager:

# Bad
class train_model:
class speedController:
class TM:
```

### 6.3 Function and Variable Names

Use **snake_case** (lowercase with underscores).

```python
# Good
def calculate_speed():
def update_position():

current_speed = 45.0
block_number = 12

# Bad
def CalculateSpeed():
def updatePosition():

CurrentSpeed = 45.0
blockNumber = 12
```

**Avoid single-letter names except:**
- Loop counters: `i`, `j`, `k`
- Coordinates: `x`, `y`, `z`
- Temporary variables in list comprehensions

### 6.4 Properties and Attributes

Use **snake_case**.

**Private attributes** prefix with single underscore.

```python
class TrainModel:
    def __init__(self):
        # Public
        self.current_speed = 0
        self.position = 0
        
        # Private
        self._internal_state = {}
        self._calculation_cache = None
```

### 6.5 Method Names

Use **snake_case**.

**Private methods** prefix with single underscore.

```python
class TrainModel:
    # Public methods
    def update_speed(self, new_speed):
        pass
    
    def calculate_position(self):
        pass
    
    # Private methods
    def _validate_input(self, value):
        pass
    
    def _internal_calculation(self):
        pass
```

### 6.6 Constant Names

Use **UPPER_SNAKE_CASE**.

Define at module level.

```python
# Good
MAX_SPEED = 70
EMERGENCY_BRAKE_DECEL = -2.73
DEFAULT_TRAIN_MASS = 40900
GRAVITY = 9.81

# Bad
maxSpeed = 70
EmergencyBrakeDecel = -2.73
```

---

## 7. Exception Handling

**Always specify exception type.** Never use bare `except:`.

```python
# Good
try:
    data = json.load(file)
except FileNotFoundError:
    print(f"File not found: {filename}")
    data = {}
except json.JSONDecodeError as e:
    print(f"Invalid JSON: {e}")
    data = {}

# Bad
try:
    data = json.load(file)
except:
    pass
```

**Keep try block minimal:**
```python
# Good
try:
    with open(filename, 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    data = {}

# Process data here (outside try block)
process(data)

# Bad - too much in try
try:
    with open(filename, 'r') as f:
        data = json.load(f)
    process(data)
    more_processing(data)
    even_more_stuff()
except:
    pass
```

---

## 8. Recommendations

### Comparisons to None

Use `is` or `is not`, never equality operators.

```python
# Good
if foo is not None:
    pass

# Bad
if foo != None:
    pass

if not foo is None:  # Less readable
    pass
```

### Exception Inheritance

Derive from `Exception`, not `BaseException`.

```python
# Good
class TrainError(Exception):
    pass

# Bad
class TrainError(BaseException):
    pass
```

### Resource Management

Use `with` statement for resource cleanup.

```python
# Good
with open(filename, 'r') as f:
    data = f.read()

# Acceptable
try:
    f = open(filename, 'r')
    data = f.read()
finally:
    f.close()
```

### Return Statements

Be consistent. Either all return expressions or all return None explicitly.

```python
# Good
def get_speed(self):
    if self.moving:
        return self.speed
    else:
        return 0

# Bad - inconsistent
def get_speed(self):
    if self.moving:
        return self.speed
    # Implicit return None
```

### Boolean Comparisons

Don't compare to `True` or `False` using `==`.

```python
# Good
if is_moving:
    pass

if not is_stopped:
    pass

# Bad
if is_moving == True:
    pass

if is_stopped is False:
    pass
```

### String Methods

Use string methods instead of `string` module.

```python
# Good
name.startswith("Train")
name.endswith(".json")

# Bad
import string
string.startswith(name, "Train")
```

---

## Summary Checklist

Before committing code, verify:

- [ ] All names follow conventions (classes PascalCase, functions/variables snake_case, constants UPPER_SNAKE_CASE)
- [ ] 4 spaces indentation (no tabs)
- [ ] Lines under 88 characters
- [ ] Imports organized (stdlib, third-party, local)
- [ ] Docstrings for all public functions/classes
- [ ] Specific exception types (no bare except)
- [ ] No magic numbers (use named constants)
- [ ] Comments are current and accurate
- [ ] No debug print() statements
- [ ] Double quotes for strings
- [ ] Proper whitespace around operators

---