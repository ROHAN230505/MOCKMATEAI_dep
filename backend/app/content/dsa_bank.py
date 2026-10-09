"""
Curated DSA problem bank (Section 8's `dsa_problems`, Phase 7).

## The execution contract

Every problem asks the candidate to implement one named function. A test case is
`{"args": [...], "expected": ...}`, and the runner calls the function with those
arguments and compares the result for equality. Deliberately the simplest
contract that works: it needs no parser, no stdin marshalling, and no per-language
harness, so the same test cases would drive a Python runner in the browser or any
other runtime later.

## Reference solutions never leave this module

Each entry carries a `reference` implementation. It exists for one reason: the
test cases are verified by *executing* it against them
(`tests/test_content_banks.py`), rather than by my having asserted that they look
right. An expected value nobody has run is a guess, and a wrong hidden test case
would fail a correct candidate solution with no way for them to find out why.

`reference` is stripped in `build_rows()` and is not a column on `dsa_problems`,
so there is no path by which it can reach a client. `tests/test_dsa_api.py` pins
that the API response never contains it.
"""
from app.models.enums import DSATopic, Difficulty

# ---------------------------------------------------------------------------
# Reference solutions. Server-side only; see the module docstring.
# ---------------------------------------------------------------------------


def _two_sum(nums, target):
    seen = {}
    for index, value in enumerate(nums):
        if target - value in seen:
            return [seen[target - value], index]
        seen[value] = index
    return []


def _max_subarray(nums):
    best = current = nums[0]
    for value in nums[1:]:
        current = max(value, current + value)
        best = max(best, current)
    return best


def _reverse_words(text):
    return " ".join(reversed(text.split()))


def _is_palindrome(text):
    cleaned = [character.lower() for character in text if character.isalnum()]
    return cleaned == cleaned[::-1]


def _binary_search(nums, target):
    low, high = 0, len(nums) - 1
    while low <= high:
        middle = (low + high) // 2
        if nums[middle] == target:
            return middle
        if nums[middle] < target:
            low = middle + 1
        else:
            high = middle - 1
    return -1


def _climb_stairs(n):
    previous, current = 1, 1
    for _ in range(n - 1):
        previous, current = current, previous + current
    return current


def _max_meetings(intervals):
    count = 0
    finished_at = float("-inf")
    for start, end in sorted(intervals, key=lambda pair: pair[1]):
        if start >= finished_at:
            count += 1
            finished_at = end
    return count


def _count_components(n, edges):
    parent = list(range(n))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in edges:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b
    return len({find(node) for node in range(n)})


# Each entry: slug, title, topic, difficulty, statement, constraints, function


# Shared by the tree problems: level-order lists use 2i+1 / 2i+2 for children
# and None for a missing node, which is the convention candidates already know.
def _children(tree, index):
    return 2 * index + 1, 2 * index + 2


def _exists(tree, index):
    return index < len(tree) and tree[index] is not None

def _move_zeroes(nums):
    out = [v for v in nums if v != 0]
    return out + [0] * (len(nums) - len(out))

def _product_except_self(nums):
    n = len(nums)
    out = [1] * n
    prefix = 1
    for i in range(n):
        out[i] = prefix
        prefix *= nums[i]
    suffix = 1
    for i in range(n - 1, -1, -1):
        out[i] *= suffix
        suffix *= nums[i]
    return out

def _rotate_array(nums, k):
    if not nums:
        return []
    k %= len(nums)
    return nums[-k:] + nums[:-k] if k else list(nums)

def _majority_element(nums):
    count = 0
    candidate = None
    for value in nums:
        if count == 0:
            candidate = value
        count += 1 if value == candidate else -1
    return candidate

def _merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda pair: pair[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged

def _find_duplicate(nums):
    slow = fast = nums[0]
    while True:
        slow = nums[slow]
        fast = nums[nums[fast]]
        if slow == fast:
            break
    slow = nums[0]
    while slow != fast:
        slow = nums[slow]
        fast = nums[fast]
    return slow

def _max_profit(prices):
    best = 0
    cheapest = None
    for price in prices:
        if cheapest is None or price < cheapest:
            cheapest = price
        elif price - cheapest > best:
            best = price - cheapest
    return best

def _is_anagram(a, b):
    return sorted(a) == sorted(b)

def _longest_common_prefix(words):
    if not words:
        return ""
    prefix = words[0]
    for word in words[1:]:
        while not word.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix

def _first_unique_char(text):
    counts = {}
    for character in text:
        counts[character] = counts.get(character, 0) + 1
    for index, character in enumerate(text):
        if counts[character] == 1:
            return index
    return -1

def _group_anagrams(words):
    groups = {}
    for word in words:
        key = "".join(sorted(word))
        groups.setdefault(key, []).append(word)
    return sorted([sorted(group) for group in groups.values()])

def _is_valid_parentheses(text):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for character in text:
        if character in "([{":
            stack.append(character)
        elif character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return False
    return not stack

def _length_of_longest_substring(text):
    last_seen = {}
    best = 0
    start = 0
    for index, character in enumerate(text):
        if character in last_seen and last_seen[character] >= start:
            start = last_seen[character] + 1
        last_seen[character] = index
        best = max(best, index - start + 1)
    return best

def _reverse_list(values):
    return values[::-1]

def _middle_node(values):
    if not values:
        return None
    return values[len(values) // 2]

def _remove_nth_from_end(values, n):
    if n <= 0 or n > len(values):
        return list(values)
    index = len(values) - n
    return values[:index] + values[index + 1:]

def _merge_two_sorted(a, b):
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out

def _has_cycle(values, pos):
    return 0 <= pos < len(values)

def _max_depth(tree):
    def walk(index):
        if not _exists(tree, index):
            return 0
        left, right = _children(tree, index)
        return 1 + max(walk(left), walk(right))
    return walk(0)

def _count_leaves(tree):
    total = 0
    for index, value in enumerate(tree):
        if value is None:
            continue
        left, right = _children(tree, index)
        if not _exists(tree, left) and not _exists(tree, right):
            total += 1
    return total

def _is_same_tree(a, b):
    length = max(len(a), len(b))
    for index in range(length):
        left = a[index] if index < len(a) else None
        right = b[index] if index < len(b) else None
        if left != right:
            return False
    return True

def _tree_sum(tree):
    return sum(value for value in tree if value is not None)

def _level_order(tree):
    levels = []
    index = 0
    width = 1
    while index < len(tree):
        level = [v for v in tree[index:index + width] if v is not None]
        if level:
            levels.append(level)
        index += width
        width *= 2
    return levels

def _is_balanced(tree):
    def depth(index):
        if not _exists(tree, index):
            return 0, True
        left, right = _children(tree, index)
        left_depth, left_ok = depth(left)
        right_depth, right_ok = depth(right)
        ok = left_ok and right_ok and abs(left_depth - right_depth) <= 1
        return 1 + max(left_depth, right_depth), ok
    return depth(0)[1]

def _number_of_islands(grid):
    if not grid or not grid[0]:
        return 0
    rows, cols = len(grid), len(grid[0])
    seen = set()
    islands = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != 1 or (r, c) in seen:
                continue
            islands += 1
            stack = [(r, c)]
            seen.add((r, c))
            while stack:
                cr, cc = stack.pop()
                for nr, nc in ((cr+1, cc), (cr-1, cc), (cr, cc+1), (cr, cc-1)):
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 1 and (nr, nc) not in seen:
                        seen.add((nr, nc))
                        stack.append((nr, nc))
    return islands

def _can_finish(num_courses, prerequisites):
    graph = {i: [] for i in range(num_courses)}
    indegree = [0] * num_courses
    for course, needs in prerequisites:
        graph[needs].append(course)
        indegree[course] += 1
    queue = [i for i in range(num_courses) if indegree[i] == 0]
    done = 0
    while queue:
        node = queue.pop()
        done += 1
        for nxt in graph[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return done == num_courses

def _count_provinces(is_connected):
    n = len(is_connected)
    seen = set()
    provinces = 0
    for start in range(n):
        if start in seen:
            continue
        provinces += 1
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for other in range(n):
                if is_connected[node][other] == 1 and other not in seen:
                    seen.add(other)
                    stack.append(other)
    return provinces

def _shortest_path_length(n, edges, source, target):
    graph = {i: [] for i in range(n)}
    for a, b in edges:
        graph[a].append(b)
        graph[b].append(a)
    if source == target:
        return 0
    seen = {source}
    frontier = [source]
    steps = 0
    while frontier:
        steps += 1
        nxt = []
        for node in frontier:
            for other in graph[node]:
                if other == target:
                    return steps
                if other not in seen:
                    seen.add(other)
                    nxt.append(other)
        frontier = nxt
    return -1

def _house_robber(nums):
    previous = current = 0
    for value in nums:
        previous, current = current, max(current, previous + value)
    return current

def _coin_change(coins, amount):
    best = [0] + [float("inf")] * amount
    for value in range(1, amount + 1):
        for coin in coins:
            if coin <= value and best[value - coin] + 1 < best[value]:
                best[value] = best[value - coin] + 1
    return -1 if best[amount] == float("inf") else best[amount]

def _length_of_lis(nums):
    if not nums:
        return 0
    best = [1] * len(nums)
    for i in range(1, len(nums)):
        for j in range(i):
            if nums[j] < nums[i]:
                best[i] = max(best[i], best[j] + 1)
    return max(best)

def _unique_paths(rows, cols):
    if rows <= 0 or cols <= 0:
        return 0
    row = [1] * cols
    for _ in range(1, rows):
        for c in range(1, cols):
            row[c] += row[c - 1]
    return row[-1]

def _lcs_length(a, b):
    grid = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                grid[i][j] = grid[i - 1][j - 1] + 1
            else:
                grid[i][j] = max(grid[i - 1][j], grid[i][j - 1])
    return grid[len(a)][len(b)]

def _edit_distance(a, b):
    grid = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        grid[i][0] = i
    for j in range(len(b) + 1):
        grid[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                grid[i][j] = grid[i - 1][j - 1]
            else:
                grid[i][j] = 1 + min(grid[i - 1][j], grid[i][j - 1], grid[i - 1][j - 1])
    return grid[len(a)][len(b)]

def _generate_parentheses(n):
    out = []
    def build(current, opened, closed):
        if len(current) == 2 * n:
            out.append(current)
            return
        if opened < n:
            build(current + "(", opened + 1, closed)
        if closed < opened:
            build(current + ")", opened, closed + 1)
    build("", 0, 0)
    return sorted(out)

def _subsets(nums):
    out = [[]]
    for value in nums:
        out += [existing + [value] for existing in out]
    return sorted(out)

def _permutations(nums):
    if not nums:
        return [[]]
    out = []
    for index, value in enumerate(nums):
        for rest in _permutations(nums[:index] + nums[index + 1:]):
            out.append([value] + rest)
    return sorted(out)

def _combination_sum(candidates, target):
    out = []
    ordered = sorted(candidates)
    def build(start, remaining, current):
        if remaining == 0:
            out.append(list(current))
            return
        for index in range(start, len(ordered)):
            value = ordered[index]
            if value > remaining:
                break
            current.append(value)
            build(index, remaining - value, current)
            current.pop()
    build(0, target, [])
    return sorted(out)

def _search_insert(nums, target):
    low, high = 0, len(nums)
    while low < high:
        mid = (low + high) // 2
        if nums[mid] < target:
            low = mid + 1
        else:
            high = mid
    return low

def _kth_largest(nums, k):
    return sorted(nums, reverse=True)[k - 1]

def _sort_colors(nums):
    counts = [0, 0, 0]
    for value in nums:
        counts[value] += 1
    return [0] * counts[0] + [1] * counts[1] + [2] * counts[2]

def _search_rotated(nums, target):
    low, high = 0, len(nums) - 1
    while low <= high:
        mid = (low + high) // 2
        if nums[mid] == target:
            return mid
        if nums[low] <= nums[mid]:
            if nums[low] <= target < nums[mid]:
                high = mid - 1
            else:
                low = mid + 1
        else:
            if nums[mid] < target <= nums[high]:
                low = mid + 1
            else:
                high = mid - 1
    return -1


# name, starter code, sample cases, hidden cases, reference.
BANK: list[dict] = [
    {
        "slug": "two-sum",
        "title": "Two Sum",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.EASY,
        "statement_text": (
            "Given a list of integers `nums` and an integer `target`, return the indices of the "
            "two numbers that add up to `target`, as a list in increasing order.\n\n"
            "Exactly one such pair exists, and you may not use the same element twice."
        ),
        "constraints_text": "2 <= len(nums) <= 10,000\n-10^9 <= nums[i], target <= 10^9",
        "function_name": "two_sum",
        "starter_code": "def two_sum(nums, target):\n    # Return [i, j] with i < j and nums[i] + nums[j] == target.\n    pass\n",
        "sample": [
            {"args": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"args": [[3, 2, 4], 6], "expected": [1, 2]},
        ],
        "hidden": [
            {"args": [[3, 3], 6], "expected": [0, 1]},
            {"args": [[-1, -2, -3, -4, -5], -8], "expected": [2, 4]},
            {"args": [[0, 4, 3, 0], 0], "expected": [0, 3]},
            {"args": [[1, 5, 3, 7, 9, 2], 11], "expected": [4, 5]},
        ],
        "reference": _two_sum,
    },
    {
        "slug": "maximum-subarray",
        "title": "Maximum Subarray Sum",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": (
            "Given a list of integers `nums`, find the contiguous subarray with the largest sum "
            "and return that sum.\n\n"
            "The subarray must contain at least one element, so an all-negative list returns its "
            "largest (least negative) element."
        ),
        "constraints_text": "1 <= len(nums) <= 100,000\n-10^4 <= nums[i] <= 10^4",
        "function_name": "max_subarray",
        "starter_code": "def max_subarray(nums):\n    # Return the largest sum of any contiguous subarray.\n    pass\n",
        "sample": [
            {"args": [[-2, 1, -3, 4, -1, 2, 1, -5, 4]], "expected": 6},
            {"args": [[1]], "expected": 1},
        ],
        "hidden": [
            {"args": [[5, 4, -1, 7, 8]], "expected": 23},
            {"args": [[-1]], "expected": -1},
            {"args": [[-2, -1]], "expected": -1},
            {"args": [[-5, -2, -8]], "expected": -2},
            {"args": [[2, -1, 2, -1, 2]], "expected": 4},
        ],
        "reference": _max_subarray,
    },
    {
        "slug": "reverse-words",
        "title": "Reverse the Words in a String",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": (
            "Given a string `text`, return a string with the order of the words reversed.\n\n"
            "Words are runs of non-space characters. Collapse repeated spaces and drop leading and "
            "trailing ones, so the result has exactly one space between words."
        ),
        "constraints_text": "0 <= len(text) <= 10,000",
        "function_name": "reverse_words",
        "starter_code": "def reverse_words(text):\n    # Return the words of `text` in reverse order, single-spaced.\n    pass\n",
        "sample": [
            {"args": ["the sky is blue"], "expected": "blue is sky the"},
            {"args": ["  hello   world  "], "expected": "world hello"},
        ],
        "hidden": [
            {"args": ["hello"], "expected": "hello"},
            {"args": ["a b c d"], "expected": "d c b a"},
            {"args": [""], "expected": ""},
            {"args": ["   "], "expected": ""},
        ],
        "reference": _reverse_words,
    },
    {
        "slug": "valid-palindrome",
        "title": "Valid Palindrome",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": (
            "Given a string `text`, return `True` if it reads the same forwards and backwards once "
            "you ignore everything that is not a letter or a digit, treating upper and lower case "
            "as the same.\n\nAn empty string counts as a palindrome."
        ),
        "constraints_text": "0 <= len(text) <= 200,000",
        "function_name": "is_palindrome",
        "starter_code": "def is_palindrome(text):\n    # Return True if `text` is a palindrome, ignoring case and punctuation.\n    pass\n",
        "sample": [
            {"args": ["A man, a plan, a canal: Panama"], "expected": True},
            {"args": ["race a car"], "expected": False},
        ],
        "hidden": [
            {"args": [""], "expected": True},
            {"args": [" "], "expected": True},
            {"args": ["0P"], "expected": False},
            {"args": [".,"], "expected": True},
            {"args": ["ab_a"], "expected": True},
            {"args": ["Was it a car or a cat I saw?"], "expected": True},
        ],
        "reference": _is_palindrome,
    },
]

BANK += [
    {
        "slug": "binary-search",
        "title": "Binary Search",
        "topic": DSATopic.SORTING_SEARCHING,
        "difficulty": Difficulty.EASY,
        "statement_text": (
            "Given a list `nums` sorted in ascending order and an integer `target`, return the "
            "index of `target` in `nums`, or `-1` if it is not present.\n\n"
            "Your solution should run in O(log n) time."
        ),
        "constraints_text": "0 <= len(nums) <= 100,000\nnums is sorted ascending with no duplicates",
        "function_name": "binary_search",
        "starter_code": "def binary_search(nums, target):\n    # Return the index of `target`, or -1.\n    pass\n",
        "sample": [
            {"args": [[-1, 0, 3, 5, 9, 12], 9], "expected": 4},
            {"args": [[-1, 0, 3, 5, 9, 12], 2], "expected": -1},
        ],
        "hidden": [
            {"args": [[5], 5], "expected": 0},
            {"args": [[], 1], "expected": -1},
            {"args": [[1, 2, 3, 4, 5], 1], "expected": 0},
            {"args": [[1, 2, 3, 4, 5], 5], "expected": 4},
            {"args": [[2, 4, 6, 8], 5], "expected": -1},
        ],
        "reference": _binary_search,
    },
    {
        "slug": "climbing-stairs",
        "title": "Climbing Stairs",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.EASY,
        "statement_text": (
            "You are climbing a staircase of `n` steps. Each move you may climb either 1 step or "
            "2 steps. Return the number of distinct ways to reach the top.\n\n"
            "Your solution should not be exponential - `n` goes up to 45."
        ),
        "constraints_text": "1 <= n <= 45",
        "function_name": "climb_stairs",
        "starter_code": "def climb_stairs(n):\n    # Return the number of distinct ways to climb n steps.\n    pass\n",
        "sample": [
            {"args": [2], "expected": 2},
            {"args": [3], "expected": 3},
        ],
        "hidden": [
            {"args": [1], "expected": 1},
            {"args": [5], "expected": 8},
            {"args": [10], "expected": 89},
            {"args": [45], "expected": 1836311903},
        ],
        "reference": _climb_stairs,
    },
    {
        "slug": "maximum-meetings",
        "title": "Maximum Non-Overlapping Meetings",
        "topic": DSATopic.GREEDY,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": (
            "Given a list of meetings as `[start, end]` pairs, return the largest number of them "
            "you can attend if you can only be in one meeting at a time.\n\n"
            "A meeting that ends exactly when another starts does not overlap it, so both can be "
            "attended."
        ),
        "constraints_text": "0 <= len(intervals) <= 100,000\n0 <= start < end <= 10^9",
        "function_name": "max_meetings",
        "starter_code": "def max_meetings(intervals):\n    # Return the largest number of non-overlapping meetings.\n    pass\n",
        "sample": [
            {"args": [[[1, 3], [2, 4], [3, 5]]], "expected": 2},
            {"args": [[[1, 2], [2, 3], [3, 4], [1, 3]]], "expected": 3},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[[1, 10]]], "expected": 1},
            {"args": [[[1, 4], [2, 3], [3, 5], [7, 8]]], "expected": 3},
            {"args": [[[0, 1], [0, 1], [0, 1]]], "expected": 1},
            {"args": [[[5, 6], [1, 2], [3, 4]]], "expected": 3},
        ],
        "reference": _max_meetings,
    },
    {
        "slug": "connected-components",
        "title": "Count Connected Components",
        "topic": DSATopic.GRAPHS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": (
            "You are given `n` nodes labelled `0` to `n - 1` and a list of undirected `edges`, "
            "each `[a, b]`. Return the number of connected components in the graph.\n\n"
            "A node with no edges is its own component."
        ),
        "constraints_text": "0 <= n <= 100,000\n0 <= len(edges) <= 200,000",
        "function_name": "count_components",
        "starter_code": "def count_components(n, edges):\n    # Return the number of connected components.\n    pass\n",
        "sample": [
            {"args": [5, [[0, 1], [1, 2], [3, 4]]], "expected": 2},
            {"args": [4, []], "expected": 4},
        ],
        "hidden": [
            {"args": [1, []], "expected": 1},
            {"args": [6, [[0, 1], [2, 3], [4, 5]]], "expected": 3},
            {"args": [3, [[0, 1], [1, 2], [0, 2]]], "expected": 1},
            {"args": [0, []], "expected": 0},
            {"args": [7, [[0, 1], [1, 2], [2, 0], [3, 4]]], "expected": 4},
        ],
        "reference": _count_components,
    },

    {
        "slug": "move-zeroes",
        "title": "Move Zeroes",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Given a list of integers `nums`, move every zero to the end while keeping the relative order of the non-zero elements. Return the resulting list.",
        "constraints_text": "0 <= len(nums) <= 10,000\n-10^9 <= nums[i] <= 10^9",
        "function_name": "move_zeroes",
        "starter_code": "def move_zeroes(nums):\n    # Return the list with zeroes pushed to the end, order otherwise kept.\n    pass\n",
        "sample": [
            {"args": [[0, 1, 0, 3, 12]], "expected": [1, 3, 12, 0, 0]},
            {"args": [[0, 0, 1]], "expected": [1, 0, 0]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[0]], "expected": [0]},
            {"args": [[1, 2, 3]], "expected": [1, 2, 3]},
            {"args": [[0, 0, 0]], "expected": [0, 0, 0]},
            {"args": [[4, 0, 5, 0, 0, 6]], "expected": [4, 5, 6, 0, 0, 0]},
        ],
        "reference": _move_zeroes,
    },
    {
        "slug": "product-except-self",
        "title": "Product of Array Except Self",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Given a list of integers `nums`, return a list where each position holds the product of every other element.\n\nSolve it without using division.",
        "constraints_text": "2 <= len(nums) <= 10,000\nThe product fits in a 64-bit integer.",
        "function_name": "product_except_self",
        "starter_code": "def product_except_self(nums):\n    # Return out[i] = product of all nums except nums[i].\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 4]], "expected": [24, 12, 8, 6]},
            {"args": [[-1, 1, 0, -3, 3]], "expected": [0, 0, 9, 0, 0]},
        ],
        "hidden": [
            {"args": [[2, 3]], "expected": [3, 2]},
            {"args": [[0, 0]], "expected": [0, 0]},
            {"args": [[1, 0, 3]], "expected": [0, 3, 0]},
            {"args": [[5, 1, 1, 1]], "expected": [1, 5, 5, 5]},
            {"args": [[-2, -3, -4]], "expected": [12, 8, 6]},
        ],
        "reference": _product_except_self,
    },
    {
        "slug": "rotate-array",
        "title": "Rotate Array",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Rotate the list `nums` to the right by `k` steps and return the result. `k` may be larger than the length of the list.",
        "constraints_text": "0 <= len(nums) <= 10,000\n0 <= k <= 10^9",
        "function_name": "rotate_array",
        "starter_code": "def rotate_array(nums, k):\n    # Return nums rotated right by k positions.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 4, 5, 6, 7], 3], "expected": [5, 6, 7, 1, 2, 3, 4]},
            {"args": [[-1, -100, 3, 99], 2], "expected": [3, 99, -1, -100]},
        ],
        "hidden": [
            {"args": [[], 3], "expected": []},
            {"args": [[1], 0], "expected": [1]},
            {"args": [[1, 2], 5], "expected": [2, 1]},
            {"args": [[1, 2, 3], 3], "expected": [1, 2, 3]},
            {"args": [[1, 2, 3, 4], 6], "expected": [3, 4, 1, 2]},
        ],
        "reference": _rotate_array,
    },
    {
        "slug": "majority-element",
        "title": "Majority Element",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Given a list `nums` of length n, return the element that appears more than n // 2 times. You may assume such an element always exists.",
        "constraints_text": "1 <= len(nums) <= 50,000\nA majority element is guaranteed to exist.",
        "function_name": "majority_element",
        "starter_code": "def majority_element(nums):\n    # Return the value appearing more than len(nums) // 2 times.\n    pass\n",
        "sample": [
            {"args": [[3, 2, 3]], "expected": 3},
            {"args": [[2, 2, 1, 1, 1, 2, 2]], "expected": 2},
        ],
        "hidden": [
            {"args": [[1]], "expected": 1},
            {"args": [[7, 7, 7, 1, 2]], "expected": 7},
            {"args": [[-5, -5, -5, 4]], "expected": -5},
            {"args": [[0, 0, 0, 0, 1, 2, 3]], "expected": 0},
        ],
        "reference": _majority_element,
    },
    {
        "slug": "merge-intervals",
        "title": "Merge Intervals",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Given a list of `[start, end]` intervals, merge every pair that overlaps and return the merged list sorted by start.",
        "constraints_text": "0 <= len(intervals) <= 10,000\nstart <= end for every interval",
        "function_name": "merge_intervals",
        "starter_code": "def merge_intervals(intervals):\n    # Return non-overlapping intervals sorted by start.\n    pass\n",
        "sample": [
            {"args": [[[1, 3], [2, 6], [8, 10], [15, 18]]], "expected": [[1, 6], [8, 10], [15, 18]]},
            {"args": [[[1, 4], [4, 5]]], "expected": [[1, 5]]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[[1, 4]]], "expected": [[1, 4]]},
            {"args": [[[1, 4], [2, 3]]], "expected": [[1, 4]]},
            {"args": [[[5, 6], [1, 2]]], "expected": [[1, 2], [5, 6]]},
            {"args": [[[1, 10], [2, 3], [4, 5]]], "expected": [[1, 10]]},
        ],
        "reference": _merge_intervals,
    },
    {
        "slug": "find-duplicate",
        "title": "Find the Duplicate Number",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A list `nums` holds n + 1 integers, each between 1 and n inclusive. Exactly one value is repeated, possibly many times. Return that value without modifying the list.",
        "constraints_text": "2 <= len(nums) <= 10,000\nEvery value is in [1, len(nums) - 1]",
        "function_name": "find_duplicate",
        "starter_code": "def find_duplicate(nums):\n    # Return the repeated value.\n    pass\n",
        "sample": [
            {"args": [[1, 3, 4, 2, 2]], "expected": 2},
            {"args": [[3, 1, 3, 4, 2]], "expected": 3},
        ],
        "hidden": [
            {"args": [[1, 1]], "expected": 1},
            {"args": [[2, 2, 2, 2, 2]], "expected": 2},
            {"args": [[1, 2, 3, 4, 4]], "expected": 4},
            {"args": [[4, 3, 1, 4, 2]], "expected": 4},
        ],
        "reference": _find_duplicate,
    },
    {
        "slug": "best-time-to-buy-and-sell-stock",
        "title": "Best Time to Buy and Sell Stock",
        "topic": DSATopic.ARRAYS,
        "difficulty": Difficulty.EASY,
        "statement_text": "`prices[i]` is the price of a stock on day i. Choose one day to buy and a later day to sell, and return the maximum profit. If no profit is possible, return 0.",
        "constraints_text": "0 <= len(prices) <= 100,000\n0 <= prices[i] <= 10^5",
        "function_name": "max_profit",
        "starter_code": "def max_profit(prices):\n    # Return the best profit from one buy and one later sell.\n    pass\n",
        "sample": [
            {"args": [[7, 1, 5, 3, 6, 4]], "expected": 5},
            {"args": [[7, 6, 4, 3, 1]], "expected": 0},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[5]], "expected": 0},
            {"args": [[1, 2]], "expected": 1},
            {"args": [[2, 1]], "expected": 0},
            {"args": [[3, 3, 3]], "expected": 0},
            {"args": [[1, 10, 1, 20]], "expected": 19},
        ],
        "reference": _max_profit,
    },
    {
        "slug": "valid-anagram",
        "title": "Valid Anagram",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Return True if string `b` is an anagram of string `a`, otherwise False. Comparison is case-sensitive and every character counts, including spaces.",
        "constraints_text": "0 <= len(a), len(b) <= 10,000",
        "function_name": "is_anagram",
        "starter_code": "def is_anagram(a, b):\n    # Return True if b is a rearrangement of a.\n    pass\n",
        "sample": [
            {"args": ["anagram", "nagaram"], "expected": True},
            {"args": ["rat", "car"], "expected": False},
        ],
        "hidden": [
            {"args": ["", ""], "expected": True},
            {"args": ["a", ""], "expected": False},
            {"args": ["ab", "ba"], "expected": True},
            {"args": ["aab", "abb"], "expected": False},
            {"args": ["Ab", "ab"], "expected": False},
        ],
        "reference": _is_anagram,
    },
    {
        "slug": "longest-common-prefix",
        "title": "Longest Common Prefix",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Return the longest string that every word in `words` starts with. If there is no common prefix, return an empty string.",
        "constraints_text": "0 <= len(words) <= 200\n0 <= len(words[i]) <= 200",
        "function_name": "longest_common_prefix",
        "starter_code": "def longest_common_prefix(words):\n    # Return the longest prefix shared by every word.\n    pass\n",
        "sample": [
            {"args": [["flower", "flow", "flight"]], "expected": "fl"},
            {"args": [["dog", "racecar", "car"]], "expected": ""},
        ],
        "hidden": [
            {"args": [[]], "expected": ""},
            {"args": [["alone"]], "expected": "alone"},
            {"args": [["", "abc"]], "expected": ""},
            {"args": [["abc", "abc"]], "expected": "abc"},
            {"args": [["ab", "abc", "abcd"]], "expected": "ab"},
        ],
        "reference": _longest_common_prefix,
    },
    {
        "slug": "first-unique-character",
        "title": "First Unique Character",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Return the index of the first character in `text` that appears exactly once. If no such character exists, return -1.",
        "constraints_text": "0 <= len(text) <= 100,000\n`text` contains lowercase English letters.",
        "function_name": "first_unique_char",
        "starter_code": "def first_unique_char(text):\n    # Return the index of the first non-repeating character, or -1.\n    pass\n",
        "sample": [
            {"args": ["leetcode"], "expected": 0},
            {"args": ["loveleetcode"], "expected": 2},
        ],
        "hidden": [
            {"args": [""], "expected": -1},
            {"args": ["aabb"], "expected": -1},
            {"args": ["z"], "expected": 0},
            {"args": ["abcabd"], "expected": 2},
            {"args": ["aabbccd"], "expected": 6},
        ],
        "reference": _first_unique_char,
    },
    {
        "slug": "group-anagrams",
        "title": "Group Anagrams",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Group the words in `words` so that anagrams of each other end up together.\n\nReturn a list of groups. Sort each group alphabetically, then sort the list of groups, so the result is deterministic.",
        "constraints_text": "0 <= len(words) <= 10,000\nWords contain lowercase English letters.",
        "function_name": "group_anagrams",
        "starter_code": "def group_anagrams(words):\n    # Return sorted groups of anagrams, each group sorted.\n    pass\n",
        "sample": [
            {"args": [["eat", "tea", "tan", "ate", "nat", "bat"]], "expected": [["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]},
            {"args": [["abc", "cba", "xyz"]], "expected": [["abc", "cba"], ["xyz"]]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[""]], "expected": [[""]]},
            {"args": [["a"]], "expected": [["a"]]},
            {"args": [["ab", "ba", "abc"]], "expected": [["ab", "ba"], ["abc"]]},
            {"args": [["aa", "aa"]], "expected": [["aa", "aa"]]},
        ],
        "reference": _group_anagrams,
    },
    {
        "slug": "valid-parentheses",
        "title": "Valid Parentheses",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Given a string containing only the characters `()[]{}`, return True if every bracket is closed by the matching type in the correct order.",
        "constraints_text": "0 <= len(text) <= 10,000",
        "function_name": "is_valid_parentheses",
        "starter_code": "def is_valid_parentheses(text):\n    # Return True if the brackets are balanced and correctly nested.\n    pass\n",
        "sample": [
            {"args": ["()[]{}"], "expected": True},
            {"args": ["(]"], "expected": False},
        ],
        "hidden": [
            {"args": [""], "expected": True},
            {"args": ["("], "expected": False},
            {"args": [")"], "expected": False},
            {"args": ["([{}])"], "expected": True},
            {"args": ["([)]"], "expected": False},
            {"args": ["((()))"], "expected": True},
        ],
        "reference": _is_valid_parentheses,
    },
    {
        "slug": "longest-substring-without-repeating",
        "title": "Longest Substring Without Repeating Characters",
        "topic": DSATopic.STRINGS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return the length of the longest substring of `text` that contains no repeated character.",
        "constraints_text": "0 <= len(text) <= 100,000",
        "function_name": "length_of_longest_substring",
        "starter_code": "def length_of_longest_substring(text):\n    # Return the length of the longest repeat-free substring.\n    pass\n",
        "sample": [
            {"args": ["abcabcbb"], "expected": 3},
            {"args": ["bbbbb"], "expected": 1},
        ],
        "hidden": [
            {"args": [""], "expected": 0},
            {"args": ["a"], "expected": 1},
            {"args": ["pwwkew"], "expected": 3},
            {"args": ["abcdef"], "expected": 6},
            {"args": ["dvdf"], "expected": 3},
            {"args": ["tmmzuxt"], "expected": 5},
        ],
        "reference": _length_of_longest_substring,
    },
    {
        "slug": "reverse-linked-list",
        "title": "Reverse a Linked List",
        "topic": DSATopic.LINKED_LISTS,
        "difficulty": Difficulty.EASY,
        "statement_text": "A linked list is given as a list of its values in order, head first. Return the values of the reversed list.\n\nSolve it as you would with pointers: walk the sequence once, building the result as you go.",
        "constraints_text": "0 <= length <= 10,000",
        "function_name": "reverse_list",
        "starter_code": "def reverse_list(values):\n    # Return the node values in reverse order.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 4, 5]], "expected": [5, 4, 3, 2, 1]},
            {"args": [[1, 2]], "expected": [2, 1]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[1]], "expected": [1]},
            {"args": [[1, 1, 2]], "expected": [2, 1, 1]},
            {"args": [[5, 4, 3, 2, 1]], "expected": [1, 2, 3, 4, 5]},
        ],
        "reference": _reverse_list,
    },
    {
        "slug": "middle-of-linked-list",
        "title": "Middle of a Linked List",
        "topic": DSATopic.LINKED_LISTS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Given a linked list as a list of values, return the value of the middle node. If there are two middle nodes, return the second one. Return None for an empty list.\n\nThe intended approach is the slow/fast two-pointer walk in a single pass.",
        "constraints_text": "0 <= length <= 10,000",
        "function_name": "middle_node",
        "starter_code": "def middle_node(values):\n    # Return the middle value, the second one if the length is even.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 4, 5]], "expected": 3},
            {"args": [[1, 2, 3, 4, 5, 6]], "expected": 4},
        ],
        "hidden": [
            {"args": [[]], "expected": None},
            {"args": [[1]], "expected": 1},
            {"args": [[1, 2]], "expected": 2},
            {"args": [[7, 7, 7]], "expected": 7},
        ],
        "reference": _middle_node,
    },
    {
        "slug": "remove-nth-from-end",
        "title": "Remove the Nth Node From the End",
        "topic": DSATopic.LINKED_LISTS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Given a linked list as a list of values and an integer `n`, remove the nth node counting from the end and return the remaining values. If `n` is out of range, return the list unchanged.",
        "constraints_text": "0 <= length <= 10,000\n1 <= n <= length, when valid",
        "function_name": "remove_nth_from_end",
        "starter_code": "def remove_nth_from_end(values, n):\n    # Return the values with the nth-from-last node removed.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 4, 5], 2], "expected": [1, 2, 3, 5]},
            {"args": [[1], 1], "expected": []},
        ],
        "hidden": [
            {"args": [[], 1], "expected": []},
            {"args": [[1, 2], 2], "expected": [2]},
            {"args": [[1, 2, 3], 3], "expected": [2, 3]},
            {"args": [[1, 2, 3], 5], "expected": [1, 2, 3]},
            {"args": [[9, 8, 7, 6], 1], "expected": [9, 8, 7]},
        ],
        "reference": _remove_nth_from_end,
    },
    {
        "slug": "merge-two-sorted-lists",
        "title": "Merge Two Sorted Lists",
        "topic": DSATopic.LINKED_LISTS,
        "difficulty": Difficulty.EASY,
        "statement_text": "Two sorted linked lists are given as lists of values. Merge them into one sorted list and return its values.\n\nDo it by walking both at once, not by concatenating and sorting.",
        "constraints_text": "0 <= len(a), len(b) <= 10,000\nBoth inputs are sorted ascending.",
        "function_name": "merge_two_sorted",
        "starter_code": "def merge_two_sorted(a, b):\n    # Return the merged sorted values.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 4], [1, 3, 4]], "expected": [1, 1, 2, 3, 4, 4]},
            {"args": [[], [0]], "expected": [0]},
        ],
        "hidden": [
            {"args": [[], []], "expected": []},
            {"args": [[1], []], "expected": [1]},
            {"args": [[1, 1], [1, 1]], "expected": [1, 1, 1, 1]},
            {"args": [[-5, 0], [-6, 7]], "expected": [-6, -5, 0, 7]},
            {"args": [[1, 2, 3], [4, 5]], "expected": [1, 2, 3, 4, 5]},
        ],
        "reference": _merge_two_sorted,
    },
    {
        "slug": "linked-list-cycle",
        "title": "Linked List Cycle",
        "topic": DSATopic.LINKED_LISTS,
        "difficulty": Difficulty.EASY,
        "statement_text": "A linked list is given as its values plus `pos`, the index the last node points back to. `pos = -1` means the list ends normally. Return True if the list contains a cycle.\n\nWith a real list you would use Floyd's slow/fast pointers; here the structure is given to you, so the task is to reason about when a cycle exists at all.",
        "constraints_text": "0 <= length <= 10,000\n-1 <= pos < length",
        "function_name": "has_cycle",
        "starter_code": "def has_cycle(values, pos):\n    # Return True if the list loops back on itself.\n    pass\n",
        "sample": [
            {"args": [[3, 2, 0, -4], 1], "expected": True},
            {"args": [[1, 2], -1], "expected": False},
        ],
        "hidden": [
            {"args": [[], -1], "expected": False},
            {"args": [[1], 0], "expected": True},
            {"args": [[1], -1], "expected": False},
            {"args": [[1, 2, 3], 2], "expected": True},
            {"args": [[1, 2, 3], -1], "expected": False},
        ],
        "reference": _has_cycle,
    },
    {
        "slug": "maximum-depth-of-binary-tree",
        "title": "Maximum Depth of a Binary Tree",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.EASY,
        "statement_text": "A binary tree is given in level order, with None where a child is missing. Return its maximum depth -- the number of nodes on the longest root-to-leaf path.",
        "constraints_text": "0 <= number of nodes <= 10,000",
        "function_name": "max_depth",
        "starter_code": "def max_depth(tree):\n    # Return the depth of the deepest root-to-leaf path.\n    pass\n",
        "sample": [
            {"args": [[3, 9, 20, None, None, 15, 7]], "expected": 3},
            {"args": [[1, None, 2]], "expected": 2},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[1]], "expected": 1},
            {"args": [[1, 2]], "expected": 2},
            {"args": [[1, 2, 3, 4, 5, 6, 7]], "expected": 3},
            {"args": [[1, 2, None, 3]], "expected": 3},
        ],
        "reference": _max_depth,
    },
    {
        "slug": "count-leaf-nodes",
        "title": "Count Leaf Nodes",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.EASY,
        "statement_text": "A binary tree is given in level order, with None for a missing child. Return the number of leaves -- nodes with no children at all.",
        "constraints_text": "0 <= number of nodes <= 10,000",
        "function_name": "count_leaves",
        "starter_code": "def count_leaves(tree):\n    # Return how many nodes have no children.\n    pass\n",
        "sample": [
            {"args": [[3, 9, 20, None, None, 15, 7]], "expected": 3},
            {"args": [[1, 2, 3]], "expected": 2},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[1]], "expected": 1},
            {"args": [[1, None, 2]], "expected": 1},
            {"args": [[1, 2, 3, 4, 5]], "expected": 3},
            {"args": [[1, 2, None, 3, 4]], "expected": 2},
        ],
        "reference": _count_leaves,
    },
    {
        "slug": "same-tree",
        "title": "Same Tree",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.EASY,
        "statement_text": "Two binary trees are given in level order with None for missing children. Return True if they have identical structure and identical values.",
        "constraints_text": "0 <= number of nodes <= 10,000",
        "function_name": "is_same_tree",
        "starter_code": "def is_same_tree(a, b):\n    # Return True if the two trees match exactly.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3], [1, 2, 3]], "expected": True},
            {"args": [[1, 2], [1, None, 2]], "expected": False},
        ],
        "hidden": [
            {"args": [[], []], "expected": True},
            {"args": [[1], []], "expected": False},
            {"args": [[1, 2, 3], [1, 2, 4]], "expected": False},
            {"args": [[1, None, 2], [1, None, 2]], "expected": True},
        ],
        "reference": _is_same_tree,
    },
    {
        "slug": "sum-of-tree-nodes",
        "title": "Sum of All Nodes",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.EASY,
        "statement_text": "A binary tree is given in level order, with None for a missing child. Return the sum of every node value.",
        "constraints_text": "0 <= number of nodes <= 10,000\n-10^6 <= value <= 10^6",
        "function_name": "tree_sum",
        "starter_code": "def tree_sum(tree):\n    # Return the total of every node value.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3]], "expected": 6},
            {"args": [[5, None, -3]], "expected": 2},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[7]], "expected": 7},
            {"args": [[1, 2, 3, 4, 5, 6, 7]], "expected": 28},
            {"args": [[-1, -2, -3]], "expected": -6},
            {"args": [[0, None, 0]], "expected": 0},
        ],
        "reference": _tree_sum,
    },
    {
        "slug": "level-order-traversal",
        "title": "Level Order Traversal",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A binary tree is given in level order with None for missing children. Return its values grouped by depth: one list per level, top to bottom, left to right, with missing nodes omitted. Levels that are entirely empty are omitted too.",
        "constraints_text": "0 <= number of nodes <= 10,000",
        "function_name": "level_order",
        "starter_code": "def level_order(tree):\n    # Return a list of lists, one per level.\n    pass\n",
        "sample": [
            {"args": [[3, 9, 20, None, None, 15, 7]], "expected": [[3], [9, 20], [15, 7]]},
            {"args": [[1]], "expected": [[1]]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[1, 2, 3]], "expected": [[1], [2, 3]]},
            {"args": [[1, None, 2]], "expected": [[1], [2]]},
            {"args": [[1, 2, 3, 4, None, None, 7]], "expected": [[1], [2, 3], [4, 7]]},
        ],
        "reference": _level_order,
    },
    {
        "slug": "balanced-binary-tree",
        "title": "Balanced Binary Tree",
        "topic": DSATopic.TREES,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A binary tree is given in level order with None for missing children. Return True if it is height-balanced: for every node, the depths of its two subtrees differ by at most one.",
        "constraints_text": "0 <= number of nodes <= 10,000",
        "function_name": "is_balanced",
        "starter_code": "def is_balanced(tree):\n    # Return True if every node's subtrees differ in depth by at most 1.\n    pass\n",
        "sample": [
            {"args": [[3, 9, 20, None, None, 15, 7]], "expected": True},
            {"args": [[1, 2, 2, 3, 3, None, None, 4, 4]], "expected": False},
        ],
        "hidden": [
            {"args": [[]], "expected": True},
            {"args": [[1]], "expected": True},
            {"args": [[1, 2]], "expected": True},
            {"args": [[1, 2, None, 3]], "expected": False},
            {"args": [[1, 2, 3, 4, 5, 6, 7]], "expected": True},
        ],
        "reference": _is_balanced,
    },
    {
        "slug": "number-of-islands",
        "title": "Number of Islands",
        "topic": DSATopic.GRAPHS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A grid of 0s and 1s is given, where 1 is land and 0 is water. Return the number of islands -- groups of 1s connected horizontally or vertically. Diagonals do not connect.",
        "constraints_text": "0 <= rows, cols <= 300\nEach cell is 0 or 1",
        "function_name": "number_of_islands",
        "starter_code": "def number_of_islands(grid):\n    # Return how many connected groups of 1s the grid contains.\n    pass\n",
        "sample": [
            {"args": [[[1, 1, 0], [0, 1, 0], [0, 0, 1]]], "expected": 2},
            {"args": [[[1, 0], [0, 1]]], "expected": 2},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[[0]]], "expected": 0},
            {"args": [[[1]]], "expected": 1},
            {"args": [[[1, 1], [1, 1]]], "expected": 1},
            {"args": [[[0, 0], [0, 0]]], "expected": 0},
            {"args": [[[1, 0, 1, 0, 1]]], "expected": 3},
        ],
        "reference": _number_of_islands,
    },
    {
        "slug": "course-schedule",
        "title": "Course Schedule",
        "topic": DSATopic.GRAPHS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "There are `num_courses` courses numbered 0 to num_courses - 1. `prerequisites[i] = [a, b]` means course b must be taken before course a. Return True if every course can be completed.\n\nEquivalently: return True if the dependency graph has no cycle.",
        "constraints_text": "1 <= num_courses <= 2,000\n0 <= len(prerequisites) <= 5,000",
        "function_name": "can_finish",
        "starter_code": "def can_finish(num_courses, prerequisites):\n    # Return True if all courses can be completed.\n    pass\n",
        "sample": [
            {"args": [2, [[1, 0]]], "expected": True},
            {"args": [2, [[1, 0], [0, 1]]], "expected": False},
        ],
        "hidden": [
            {"args": [1, []], "expected": True},
            {"args": [3, [[1, 0], [2, 1]]], "expected": True},
            {"args": [3, [[0, 1], [1, 2], [2, 0]]], "expected": False},
            {"args": [4, [[1, 0], [2, 0], [3, 1]]], "expected": True},
        ],
        "reference": _can_finish,
    },
    {
        "slug": "number-of-provinces",
        "title": "Number of Provinces",
        "topic": DSATopic.GRAPHS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "`is_connected[i][j] = 1` means city i and city j are directly connected. A province is a group of cities connected directly or indirectly. Return the number of provinces.",
        "constraints_text": "1 <= n <= 200\nis_connected[i][i] == 1 and the matrix is symmetric",
        "function_name": "count_provinces",
        "starter_code": "def count_provinces(is_connected):\n    # Return the number of connected groups of cities.\n    pass\n",
        "sample": [
            {"args": [[[1, 1, 0], [1, 1, 0], [0, 0, 1]]], "expected": 2},
            {"args": [[[1, 0, 0], [0, 1, 0], [0, 0, 1]]], "expected": 3},
        ],
        "hidden": [
            {"args": [[[1]]], "expected": 1},
            {"args": [[[1, 1], [1, 1]]], "expected": 1},
            {"args": [[[1, 0], [0, 1]]], "expected": 2},
            {"args": [[[1, 1, 0], [1, 1, 1], [0, 1, 1]]], "expected": 1},
        ],
        "reference": _count_provinces,
    },
    {
        "slug": "shortest-path-unweighted",
        "title": "Shortest Path in an Unweighted Graph",
        "topic": DSATopic.GRAPHS,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "An undirected graph has `n` nodes numbered 0 to n - 1 and the given `edges`. Return the fewest edges on any path from `source` to `target`, or -1 if they are not connected.",
        "constraints_text": "1 <= n <= 10,000\n0 <= source, target < n",
        "function_name": "shortest_path_length",
        "starter_code": "def shortest_path_length(n, edges, source, target):\n    # Return the number of edges on the shortest path, or -1.\n    pass\n",
        "sample": [
            {"args": [5, [[0, 1], [1, 2], [2, 3], [3, 4]], 0, 4], "expected": 4},
            {"args": [4, [[0, 1], [2, 3]], 0, 3], "expected": -1},
        ],
        "hidden": [
            {"args": [1, [], 0, 0], "expected": 0},
            {"args": [2, [[0, 1]], 0, 1], "expected": 1},
            {"args": [3, [[0, 1], [1, 2]], 0, 2], "expected": 2},
            {"args": [4, [[0, 1], [1, 2], [0, 3]], 3, 2], "expected": 3},
        ],
        "reference": _shortest_path_length,
    },
    {
        "slug": "house-robber",
        "title": "House Robber",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "`nums[i]` is the money in house i. You cannot rob two adjacent houses. Return the most you can take.",
        "constraints_text": "0 <= len(nums) <= 10,000\n0 <= nums[i] <= 10^4",
        "function_name": "house_robber",
        "starter_code": "def house_robber(nums):\n    # Return the maximum total from non-adjacent houses.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3, 1]], "expected": 4},
            {"args": [[2, 7, 9, 3, 1]], "expected": 12},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[5]], "expected": 5},
            {"args": [[2, 1]], "expected": 2},
            {"args": [[1, 2]], "expected": 2},
            {"args": [[0, 0, 0]], "expected": 0},
            {"args": [[5, 1, 1, 5]], "expected": 10},
        ],
        "reference": _house_robber,
    },
    {
        "slug": "coin-change",
        "title": "Coin Change",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Given coin denominations `coins` and a target `amount`, return the fewest coins that sum to the amount. Return -1 if it cannot be made. You have unlimited coins of each kind.",
        "constraints_text": "1 <= len(coins) <= 12\n0 <= amount <= 10,000",
        "function_name": "coin_change",
        "starter_code": "def coin_change(coins, amount):\n    # Return the fewest coins summing to amount, or -1.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 5], 11], "expected": 3},
            {"args": [[2], 3], "expected": -1},
        ],
        "hidden": [
            {"args": [[1], 0], "expected": 0},
            {"args": [[2], 1], "expected": -1},
            {"args": [[1, 5, 10], 18], "expected": 5},
            {"args": [[7], 14], "expected": 2},
            {"args": [[3, 5], 7], "expected": -1},
            {"args": [[5], 0], "expected": 0},
        ],
        "reference": _coin_change,
    },
    {
        "slug": "longest-increasing-subsequence",
        "title": "Longest Increasing Subsequence",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return the length of the longest strictly increasing subsequence of `nums`. The elements need not be adjacent, but must keep their original order.",
        "constraints_text": "0 <= len(nums) <= 2,500\n-10^4 <= nums[i] <= 10^4",
        "function_name": "length_of_lis",
        "starter_code": "def length_of_lis(nums):\n    # Return the length of the longest increasing subsequence.\n    pass\n",
        "sample": [
            {"args": [[10, 9, 2, 5, 3, 7, 101, 18]], "expected": 4},
            {"args": [[0, 1, 0, 3, 2, 3]], "expected": 4},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[1]], "expected": 1},
            {"args": [[7, 7, 7]], "expected": 1},
            {"args": [[5, 4, 3, 2, 1]], "expected": 1},
            {"args": [[1, 2, 3, 4]], "expected": 4},
            {"args": [[3, 1, 2]], "expected": 2},
        ],
        "reference": _length_of_lis,
    },
    {
        "slug": "unique-paths",
        "title": "Unique Paths",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A robot starts at the top-left of a `rows` x `cols` grid and may move only right or down. Return how many distinct paths reach the bottom-right corner.",
        "constraints_text": "1 <= rows, cols <= 100",
        "function_name": "unique_paths",
        "starter_code": "def unique_paths(rows, cols):\n    # Return the number of right/down paths across the grid.\n    pass\n",
        "sample": [
            {"args": [3, 7], "expected": 28},
            {"args": [3, 2], "expected": 3},
        ],
        "hidden": [
            {"args": [1, 1], "expected": 1},
            {"args": [1, 10], "expected": 1},
            {"args": [10, 1], "expected": 1},
            {"args": [2, 2], "expected": 2},
            {"args": [4, 4], "expected": 20},
            {"args": [5, 3], "expected": 15},
        ],
        "reference": _unique_paths,
    },
    {
        "slug": "longest-common-subsequence",
        "title": "Longest Common Subsequence",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return the length of the longest subsequence present in both strings `a` and `b`. A subsequence keeps order but need not be contiguous.",
        "constraints_text": "0 <= len(a), len(b) <= 1,000",
        "function_name": "lcs_length",
        "starter_code": "def lcs_length(a, b):\n    # Return the length of the longest common subsequence.\n    pass\n",
        "sample": [
            {"args": ["abcde", "ace"], "expected": 3},
            {"args": ["abc", "def"], "expected": 0},
        ],
        "hidden": [
            {"args": ["", ""], "expected": 0},
            {"args": ["a", ""], "expected": 0},
            {"args": ["abc", "abc"], "expected": 3},
            {"args": ["abcd", "dcba"], "expected": 1},
            {"args": ["bl", "yby"], "expected": 1},
        ],
        "reference": _lcs_length,
    },
    {
        "slug": "edit-distance",
        "title": "Edit Distance",
        "topic": DSATopic.DYNAMIC_PROGRAMMING,
        "difficulty": Difficulty.HARD,
        "statement_text": "Return the minimum number of single-character insertions, deletions or substitutions needed to turn string `a` into string `b`.",
        "constraints_text": "0 <= len(a), len(b) <= 500",
        "function_name": "edit_distance",
        "starter_code": "def edit_distance(a, b):\n    # Return the minimum number of edits turning a into b.\n    pass\n",
        "sample": [
            {"args": ["horse", "ros"], "expected": 3},
            {"args": ["intention", "execution"], "expected": 5},
        ],
        "hidden": [
            {"args": ["", ""], "expected": 0},
            {"args": ["a", ""], "expected": 1},
            {"args": ["", "abc"], "expected": 3},
            {"args": ["abc", "abc"], "expected": 0},
            {"args": ["ab", "ba"], "expected": 2},
            {"args": ["sunday", "saturday"], "expected": 3},
        ],
        "reference": _edit_distance,
    },
    {
        "slug": "generate-parentheses",
        "title": "Generate Parentheses",
        "topic": DSATopic.RECURSION_BACKTRACKING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return every well-formed string of `n` pairs of parentheses, sorted alphabetically so the result does not depend on the order you explore.",
        "constraints_text": "0 <= n <= 8",
        "function_name": "generate_parentheses",
        "starter_code": "def generate_parentheses(n):\n    # Return all valid combinations, sorted.\n    pass\n",
        "sample": [
            {"args": [3], "expected": ["((()))", "(()())", "(())()", "()(())", "()()()"]},
            {"args": [1], "expected": ["()"]},
        ],
        "hidden": [
            {"args": [0], "expected": [""]},
            {"args": [2], "expected": ["(())", "()()"]},
            {"args": [4], "expected": ["(((())))", "((()()))", "((())())", "((()))()", "(()(()))", "(()()())", "(()())()", "(())(())", "(())()()", "()((()))", "()(()())", "()(())()", "()()(())", "()()()()"]},
        ],
        "reference": _generate_parentheses,
    },
    {
        "slug": "subsets",
        "title": "Subsets",
        "topic": DSATopic.RECURSION_BACKTRACKING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return every subset of the distinct integers in `nums`. Sort each subset ascending and sort the list of subsets, so the answer does not depend on traversal order.",
        "constraints_text": "0 <= len(nums) <= 10\nValues are distinct",
        "function_name": "subsets",
        "starter_code": "def subsets(nums):\n    # Return all subsets, each sorted, the whole list sorted.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3]], "expected": [[], [1], [1, 2], [1, 2, 3], [1, 3], [2], [2, 3], [3]]},
            {"args": [[0]], "expected": [[], [0]]},
        ],
        "hidden": [
            {"args": [[]], "expected": [[]]},
            {"args": [[1]], "expected": [[], [1]]},
            {"args": [[1, 2]], "expected": [[], [1], [1, 2], [2]]},
            {"args": [[-1, 0, 1]], "expected": [[], [-1], [-1, 0], [-1, 0, 1], [-1, 1], [0], [0, 1], [1]]},
        ],
        "reference": _subsets,
    },
    {
        "slug": "permutations",
        "title": "Permutations",
        "topic": DSATopic.RECURSION_BACKTRACKING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return every ordering of the distinct integers in `nums`, as a sorted list of lists.",
        "constraints_text": "0 <= len(nums) <= 7\nValues are distinct",
        "function_name": "permutations",
        "starter_code": "def permutations(nums):\n    # Return all permutations, sorted.\n    pass\n",
        "sample": [
            {"args": [[1, 2, 3]], "expected": [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]]},
            {"args": [[0, 1]], "expected": [[0, 1], [1, 0]]},
        ],
        "hidden": [
            {"args": [[]], "expected": [[]]},
            {"args": [[1]], "expected": [[1]]},
            {"args": [[2, 1]], "expected": [[1, 2], [2, 1]]},
            {"args": [[1, 2, 3, 4]], "expected": [[1, 2, 3, 4], [1, 2, 4, 3], [1, 3, 2, 4], [1, 3, 4, 2], [1, 4, 2, 3], [1, 4, 3, 2], [2, 1, 3, 4], [2, 1, 4, 3], [2, 3, 1, 4], [2, 3, 4, 1], [2, 4, 1, 3], [2, 4, 3, 1], [3, 1, 2, 4], [3, 1, 4, 2], [3, 2, 1, 4], [3, 2, 4, 1], [3, 4, 1, 2], [3, 4, 2, 1], [4, 1, 2, 3], [4, 1, 3, 2], [4, 2, 1, 3], [4, 2, 3, 1], [4, 3, 1, 2], [4, 3, 2, 1]]},
        ],
        "reference": _permutations,
    },
    {
        "slug": "combination-sum",
        "title": "Combination Sum",
        "topic": DSATopic.RECURSION_BACKTRACKING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return every combination of `candidates` that sums to `target`. Each candidate may be used any number of times. Sort each combination ascending and sort the result.",
        "constraints_text": "1 <= len(candidates) <= 30\n1 <= candidates[i], target <= 200\nCandidates are distinct",
        "function_name": "combination_sum",
        "starter_code": "def combination_sum(candidates, target):\n    # Return all combinations summing to target, sorted.\n    pass\n",
        "sample": [
            {"args": [[2, 3, 6, 7], 7], "expected": [[2, 2, 3], [7]]},
            {"args": [[2, 3, 5], 8], "expected": [[2, 2, 2, 2], [2, 3, 3], [3, 5]]},
        ],
        "hidden": [
            {"args": [[2], 1], "expected": []},
            {"args": [[1], 3], "expected": [[1, 1, 1]]},
            {"args": [[3, 5], 8], "expected": [[3, 5]]},
            {"args": [[2, 4], 6], "expected": [[2, 2, 2], [2, 4]]},
            {"args": [[7], 7], "expected": [[7]]},
        ],
        "reference": _combination_sum,
    },
    {
        "slug": "search-insert-position",
        "title": "Search Insert Position",
        "topic": DSATopic.SORTING_SEARCHING,
        "difficulty": Difficulty.EASY,
        "statement_text": "Given a sorted list of distinct integers and a `target`, return the index of the target. If it is absent, return the index where it would be inserted to keep the list sorted.",
        "constraints_text": "0 <= len(nums) <= 10,000\nnums is sorted ascending with distinct values",
        "function_name": "search_insert",
        "starter_code": "def search_insert(nums, target):\n    # Return the index of target, or where it would go.\n    pass\n",
        "sample": [
            {"args": [[1, 3, 5, 6], 5], "expected": 2},
            {"args": [[1, 3, 5, 6], 2], "expected": 1},
        ],
        "hidden": [
            {"args": [[], 1], "expected": 0},
            {"args": [[1], 0], "expected": 0},
            {"args": [[1], 2], "expected": 1},
            {"args": [[1, 3, 5, 6], 7], "expected": 4},
            {"args": [[1, 3, 5, 6], 0], "expected": 0},
        ],
        "reference": _search_insert,
    },
    {
        "slug": "kth-largest-element",
        "title": "Kth Largest Element",
        "topic": DSATopic.SORTING_SEARCHING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "Return the kth largest element in `nums`, counting duplicates. k is 1-based, so k = 1 is the maximum.",
        "constraints_text": "1 <= k <= len(nums) <= 10,000",
        "function_name": "kth_largest",
        "starter_code": "def kth_largest(nums, k):\n    # Return the kth largest value, duplicates counted.\n    pass\n",
        "sample": [
            {"args": [[3, 2, 1, 5, 6, 4], 2], "expected": 5},
            {"args": [[3, 2, 3, 1, 2, 4, 5, 5, 6], 4], "expected": 4},
        ],
        "hidden": [
            {"args": [[1], 1], "expected": 1},
            {"args": [[2, 1], 2], "expected": 1},
            {"args": [[5, 5, 5], 2], "expected": 5},
            {"args": [[-1, -2, -3], 1], "expected": -1},
            {"args": [[7, 7, 6], 3], "expected": 6},
        ],
        "reference": _kth_largest,
    },
    {
        "slug": "sort-colors",
        "title": "Sort Colors",
        "topic": DSATopic.SORTING_SEARCHING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "`nums` contains only the values 0, 1 and 2. Return the list sorted ascending, without calling a library sort.",
        "constraints_text": "0 <= len(nums) <= 10,000\nEvery value is 0, 1 or 2",
        "function_name": "sort_colors",
        "starter_code": "def sort_colors(nums):\n    # Return the list sorted, using counting rather than a library sort.\n    pass\n",
        "sample": [
            {"args": [[2, 0, 2, 1, 1, 0]], "expected": [0, 0, 1, 1, 2, 2]},
            {"args": [[2, 0, 1]], "expected": [0, 1, 2]},
        ],
        "hidden": [
            {"args": [[]], "expected": []},
            {"args": [[0]], "expected": [0]},
            {"args": [[2, 2, 2]], "expected": [2, 2, 2]},
            {"args": [[1, 0]], "expected": [0, 1]},
            {"args": [[0, 1, 2, 0, 1, 2]], "expected": [0, 0, 1, 1, 2, 2]},
        ],
        "reference": _sort_colors,
    },
    {
        "slug": "search-in-rotated-sorted-array",
        "title": "Search in a Rotated Sorted Array",
        "topic": DSATopic.SORTING_SEARCHING,
        "difficulty": Difficulty.MEDIUM,
        "statement_text": "A sorted list of distinct integers has been rotated at some unknown pivot. Return the index of `target`, or -1 if it is absent. Your solution should run in O(log n).",
        "constraints_text": "0 <= len(nums) <= 10,000\nValues are distinct",
        "function_name": "search_rotated",
        "starter_code": "def search_rotated(nums, target):\n    # Return the index of target in the rotated list, or -1.\n    pass\n",
        "sample": [
            {"args": [[4, 5, 6, 7, 0, 1, 2], 0], "expected": 4},
            {"args": [[4, 5, 6, 7, 0, 1, 2], 3], "expected": -1},
        ],
        "hidden": [
            {"args": [[], 1], "expected": -1},
            {"args": [[1], 1], "expected": 0},
            {"args": [[1], 0], "expected": -1},
            {"args": [[3, 1], 1], "expected": 1},
            {"args": [[5, 1, 2, 3, 4], 4], "expected": 4},
            {"args": [[1, 2, 3], 2], "expected": 1},
        ],
        "reference": _search_rotated,
    },
]


def build_rows() -> list[dict]:
    """
    The bank in `dsa_problems` column shape, with `reference` stripped.

    `test_cases` is stored as Section 8's `{"sample": [...], "hidden": [...]}`
    and `starter_code` as a per-language map, both matching the JSON columns. The
    function name travels inside `starter_code` implicitly, so it is also stored
    under its own key for the runner to call without parsing the source.
    """
    return [
        {
            "title": problem["title"],
            "topic": problem["topic"],
            "difficulty": problem["difficulty"],
            "statement_text": problem["statement_text"],
            "constraints_text": problem["constraints_text"],
            "starter_code": {
                "python": problem["starter_code"],
                "functionName": problem["function_name"],
            },
            "test_cases": {"sample": problem["sample"], "hidden": problem["hidden"]},
        }
        for problem in BANK
    ]
