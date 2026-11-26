"""Starter content for a North Indian hostel mess: dishes and a weekly food chart.

Portions are cooked weights per person. Costs are rupees per cooked kilogram and the
CO2e factors are coarse category estimates; both are meant to be edited per kitchen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DishSpec:
    name: str
    category: str  # breakfast | staple | dal | sabzi | special | snack | side | dessert | beverage
    portion_g: float
    cost_per_kg: float
    veg: bool = True
    piece_g: float | None = None
    slow: bool = False
    ingredients: tuple[tuple[str, int], ...] = field(default_factory=tuple)  # (name, grams per cooked kg)


_CO2_BY_CATEGORY = {
    "breakfast": 1.2,
    "staple": 1.3,
    "dal": 1.1,
    "sabzi": 0.9,
    "special": 2.0,
    "snack": 1.6,
    "side": 0.8,
    "dessert": 2.6,
    "beverage": 0.7,
}
_CO2_BY_KEYWORD = (("Chicken", 6.0), ("Paneer", 5.0), ("Egg", 3.2), ("Omelette", 3.2), ("Curd", 1.6), ("Raita", 1.6))


def co2_per_kg(spec: DishSpec) -> float:
    for keyword, factor in _CO2_BY_KEYWORD:
        if keyword in spec.name:
            return factor
    return _CO2_BY_CATEGORY[spec.category]


def _d(name, category, portion_g, cost, *, veg=True, piece=None, slow=False, ing=()):
    return DishSpec(name, category, portion_g, cost, veg, piece, slow, tuple(ing))


DISHES: tuple[DishSpec, ...] = (
    # Breakfast
    _d("Aloo Paratha", "breakfast", 220, 70, piece=110, slow=True, ing=[("Atta", 450), ("Potato", 400), ("Oil", 40)]),
    _d("Poha", "breakfast", 180, 55, ing=[("Poha", 330), ("Onion", 120), ("Peanuts", 50)]),
    _d("Idli Sambar", "breakfast", 260, 60, ing=[("Rice", 250), ("Urad dal", 90), ("Toor dal", 60), ("Vegetables", 150)]),
    _d("Masala Dosa", "breakfast", 230, 75, slow=True, ing=[("Rice", 300), ("Urad dal", 100), ("Potato", 250), ("Oil", 40)]),
    _d("Chole Bhature", "breakfast", 300, 85, slow=True, ing=[("Maida", 330), ("Chickpeas", 200), ("Oil", 80)]),
    _d("Upma", "breakfast", 180, 50, ing=[("Suji", 300), ("Vegetables", 120), ("Oil", 30)]),
    _d("Bread Omelette", "breakfast", 160, 95, veg=False, slow=True, ing=[("Bread", 400), ("Eggs", 500), ("Oil", 30)]),
    _d("Puri Bhaji", "breakfast", 240, 70, ing=[("Atta", 380), ("Potato", 380), ("Oil", 90)]),
    _d("Veg Sandwich", "breakfast", 170, 80, ing=[("Bread", 520), ("Vegetables", 300), ("Butter", 60)]),
    _d("Daliya", "breakfast", 200, 40, ing=[("Daliya", 220), ("Milk", 300), ("Sugar", 50)]),
    # Staples
    _d("Steamed Rice", "staple", 180, 45, ing=[("Rice", 380)]),
    _d("Roti", "staple", 120, 60, piece=40, ing=[("Atta", 700)]),
    _d("Jeera Rice", "staple", 180, 55, ing=[("Rice", 380), ("Ghee", 20)]),
    _d("Veg Pulao", "staple", 220, 70, ing=[("Rice", 340), ("Vegetables", 180), ("Oil", 30)]),
    _d("Veg Biryani", "special", 300, 95, ing=[("Rice", 330), ("Vegetables", 250), ("Curd", 60), ("Oil", 40)]),
    _d("Chicken Biryani", "special", 320, 190, veg=False, ing=[("Rice", 320), ("Chicken", 330), ("Curd", 60), ("Oil", 40)]),
    # Dal and gravies
    _d("Dal Tadka", "dal", 150, 60, ing=[("Toor dal", 230), ("Onion", 50), ("Ghee", 15)]),
    _d("Dal Makhani", "dal", 150, 85, ing=[("Urad dal", 220), ("Rajma", 40), ("Butter", 40), ("Cream", 30)]),
    _d("Rajma", "dal", 170, 80, ing=[("Rajma", 260), ("Onion", 90), ("Tomato", 110)]),
    _d("Chole", "dal", 170, 75, ing=[("Chickpeas", 270), ("Onion", 90), ("Tomato", 100)]),
    _d("Kadhi Pakora", "dal", 170, 65, ing=[("Curd", 350), ("Besan", 120), ("Oil", 40)]),
    _d("Sambar", "dal", 160, 55, ing=[("Toor dal", 160), ("Vegetables", 250)]),
    # Vegetables
    _d("Aloo Gobi", "sabzi", 130, 60, ing=[("Potato", 420), ("Cauliflower", 480), ("Oil", 40)]),
    _d("Mix Veg", "sabzi", 130, 65, ing=[("Vegetables", 900), ("Oil", 40)]),
    _d("Lauki Chana", "sabzi", 130, 50, ing=[("Lauki", 760), ("Chana dal", 120), ("Oil", 30)]),
    _d("Tinda Masala", "sabzi", 130, 50, ing=[("Tinda", 880), ("Oil", 40)]),
    _d("Bhindi Fry", "sabzi", 120, 80, ing=[("Bhindi", 1000), ("Oil", 60)]),
    _d("Baingan Bharta", "sabzi", 130, 60, ing=[("Baingan", 900), ("Onion", 120), ("Oil", 40)]),
    _d("Aloo Matar", "sabzi", 130, 55, ing=[("Potato", 520), ("Peas", 300), ("Oil", 35)]),
    _d("Cabbage Matar", "sabzi", 130, 45, ing=[("Cabbage", 780), ("Peas", 180), ("Oil", 30)]),
    # Specials
    _d("Palak Paneer", "special", 150, 150, ing=[("Spinach", 520), ("Paneer", 300), ("Cream", 30)]),
    _d("Paneer Butter Masala", "special", 150, 170, ing=[("Paneer", 380), ("Tomato", 300), ("Butter", 50), ("Cream", 50)]),
    _d("Kadhai Paneer", "special", 150, 170, ing=[("Paneer", 380), ("Capsicum", 200), ("Tomato", 200), ("Oil", 40)]),
    _d("Matar Paneer", "special", 150, 150, ing=[("Paneer", 300), ("Peas", 280), ("Tomato", 200)]),
    _d("Soya Chaap Masala", "special", 150, 110, ing=[("Soya chaap", 500), ("Tomato", 220), ("Cream", 40)]),
    _d("Egg Curry", "special", 160, 120, veg=False, ing=[("Eggs", 560), ("Onion", 140), ("Tomato", 160)]),
    _d("Chicken Curry", "special", 180, 210, veg=False, ing=[("Chicken", 620), ("Onion", 150), ("Tomato", 130)]),
    # Sides
    _d("Salad", "side", 50, 40, ing=[("Cucumber", 450), ("Onion", 300), ("Tomato", 300)]),
    _d("Curd", "side", 100, 70, ing=[("Curd", 1000)]),
    _d("Boondi Raita", "side", 100, 65, ing=[("Curd", 850), ("Boondi", 120)]),
    _d("Banana", "side", 100, 45, piece=100, ing=[("Banana", 1000)]),
    _d("Boiled Egg", "side", 50, 140, veg=False, piece=50, ing=[("Eggs", 1000)]),
    # Desserts
    _d("Gulab Jamun", "dessert", 80, 180, piece=40, ing=[("Khoya", 420), ("Sugar", 380), ("Maida", 90)]),
    _d("Kheer", "dessert", 120, 110, ing=[("Milk", 900), ("Rice", 70), ("Sugar", 110)]),
    _d("Suji Halwa", "dessert", 100, 120, ing=[("Suji", 250), ("Sugar", 230), ("Ghee", 140)]),
    _d("Ice Cream", "dessert", 70, 200, ing=[("Ice cream", 1000)]),
    _d("Fruit Custard", "dessert", 120, 110, ing=[("Milk", 650), ("Fruit", 300), ("Custard powder", 40)]),
    # Evening snacks
    _d("Samosa", "snack", 100, 110, piece=100, ing=[("Maida", 300), ("Potato", 480), ("Oil", 120)]),
    _d("Veg Pakora", "snack", 110, 100, ing=[("Besan", 330), ("Vegetables", 450), ("Oil", 130)]),
    _d("Maggi", "snack", 180, 90, slow=True, ing=[("Noodles", 330), ("Vegetables", 120)]),
    _d("Bread Pakora", "snack", 120, 95, ing=[("Bread", 380), ("Besan", 200), ("Potato", 250), ("Oil", 110)]),
    _d("Aloo Tikki", "snack", 120, 95, ing=[("Potato", 760), ("Oil", 90)]),
    _d("Veg Cutlet", "snack", 120, 100, ing=[("Vegetables", 520), ("Potato", 300), ("Oil", 90)]),
    _d("Bhel Puri", "snack", 130, 85, ing=[("Puffed rice", 380), ("Sev", 150), ("Onion", 150), ("Chutney", 120)]),
    _d("Vada Pav", "snack", 150, 90, piece=150, ing=[("Pav", 380), ("Potato", 420), ("Besan", 110), ("Oil", 80)]),
    _d("Sprouts Chaat", "snack", 120, 80, ing=[("Sprouts", 620), ("Onion", 150), ("Tomato", 150)]),
    _d("Biscuits", "snack", 40, 150, ing=[("Biscuits", 1000)]),
    # Beverages
    _d("Tea", "beverage", 150, 30, ing=[("Milk", 450), ("Tea leaves", 12), ("Sugar", 55)]),
    _d("Milk", "beverage", 200, 55, ing=[("Milk", 1000)]),
)

DISH_BY_NAME = {spec.name: spec for spec in DISHES}

# The weekly food chart the mess starts from. Monday first.
WEEKLY_CHART: tuple[dict[str, tuple[str, ...]], ...] = (
    {
        "breakfast": ("Poha", "Banana", "Tea"),
        "lunch": ("Steamed Rice", "Roti", "Dal Tadka", "Aloo Gobi", "Salad"),
        "snacks": ("Samosa", "Tea"),
        "dinner": ("Roti", "Steamed Rice", "Rajma", "Mix Veg", "Curd"),
    },
    {
        "breakfast": ("Idli Sambar", "Milk", "Tea"),
        "lunch": ("Steamed Rice", "Roti", "Kadhi Pakora", "Bhindi Fry", "Salad"),
        "snacks": ("Bhel Puri", "Tea"),
        "dinner": ("Roti", "Jeera Rice", "Dal Makhani", "Lauki Chana", "Suji Halwa"),
    },
    {
        "breakfast": ("Aloo Paratha", "Curd", "Tea"),
        "lunch": ("Steamed Rice", "Roti", "Chole", "Cabbage Matar", "Boondi Raita"),
        "snacks": ("Maggi", "Tea"),
        "dinner": ("Roti", "Steamed Rice", "Egg Curry", "Matar Paneer", "Dal Tadka", "Salad"),
    },
    {
        "breakfast": ("Upma", "Boiled Egg", "Tea"),
        "lunch": ("Steamed Rice", "Roti", "Sambar", "Aloo Matar", "Curd"),
        "snacks": ("Veg Pakora", "Tea"),
        "dinner": ("Roti", "Steamed Rice", "Dal Tadka", "Tinda Masala", "Kheer"),
    },
    {
        "breakfast": ("Puri Bhaji", "Milk", "Tea"),
        "lunch": ("Veg Pulao", "Roti", "Dal Makhani", "Baingan Bharta", "Boondi Raita"),
        "snacks": ("Vada Pav", "Tea"),
        "dinner": ("Roti", "Steamed Rice", "Chicken Curry", "Paneer Butter Masala", "Dal Tadka", "Salad"),
    },
    {
        "breakfast": ("Veg Sandwich", "Banana", "Tea"),
        "lunch": ("Steamed Rice", "Roti", "Rajma", "Mix Veg", "Curd"),
        "snacks": ("Aloo Tikki", "Tea"),
        "dinner": ("Roti", "Jeera Rice", "Kadhai Paneer", "Dal Tadka", "Gulab Jamun"),
    },
    {
        "breakfast": ("Chole Bhature", "Tea"),
        "lunch": ("Chicken Biryani", "Veg Biryani", "Boondi Raita", "Salad", "Ice Cream"),
        "snacks": ("Bread Pakora", "Tea"),
        "dinner": ("Roti", "Steamed Rice", "Dal Tadka", "Aloo Gobi", "Fruit Custard"),
    },
)
