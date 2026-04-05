Projected models let you create type-safe subset views of existing Pydantic models, preserving
type annotations, validators, defaults, and constraints. Below are practical examples.

## API Response Shaping

A common pattern in web APIs is to expose different subsets of a domain model depending on the
endpoint or the caller's permissions. `ProjectedModel` lets you define these views declaratively
without duplicating field definitions.

```python {test="skip"}
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field, Projected, ProjectedModel

app = FastAPI()


class User(BaseModel):
    id: int
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    hashed_password: str
    is_admin: bool = False
    created_at: datetime


class UserPublic(ProjectedModel[User]):
    id: Projected
    username: Projected


class UserAdmin(ProjectedModel[User]):
    id: Projected
    username: Projected
    email: Projected
    is_admin: Projected
    created_at: Projected


@app.get('/users/{user_id}')
def get_user(user_id: int) -> UserPublic:
    row = fetch_user(user_id)  # your DB lookup
    return UserPublic.model_validate(row)


@app.get('/admin/users/{user_id}')
def get_user_admin(user_id: int) -> UserAdmin:
    row = fetch_user(user_id)
    return UserAdmin.model_validate(row)
```

`UserPublic` and `UserAdmin` are both full `BaseModel` subclasses — they generate their own
JSON Schema, work with FastAPI's response serialization, and never expose `hashed_password`.

## Database Query Optimization

When you have a large model mirroring a database table, you can create lightweight projections
that correspond to the exact columns you `SELECT`. Field constraints like `gt` and `ge` are
preserved in every projection.

```python
from pydantic import BaseModel, Field, ValidationError, Projected, ProjectedModel


class Product(BaseModel):
    id: int
    sku: str = Field(max_length=40)
    name: str
    description: str = ''
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    category: str = 'general'
    is_active: bool = True


class ProductListing(ProjectedModel[Product]):
    id: Projected
    name: Projected
    price: Projected
    category: Projected


class ProductInventory(ProjectedModel[Product]):
    sku: Projected
    name: Projected
    stock: Projected


listing = ProductListing(id=1, name='Widget', price=9.99, category='gadgets')
print(listing.model_dump())
#> {'id': 1, 'name': 'Widget', 'price': 9.99, 'category': 'gadgets'}

inv = ProductInventory(sku='WDG-001', name='Widget', stock=42)
print(inv.model_dump())
#> {'sku': 'WDG-001', 'name': 'Widget', 'stock': 42}

# Constraints are preserved — stock must be >= 0
try:
    ProductInventory(sku='BAD', name='Oops', stock=-5)
except ValidationError as e:
    print(e.error_count())
    #> 1
```

## Nested Domain Models

For models that contain other models, you can create nested projections that pare down each
layer independently.

```python
from pydantic import BaseModel, Projected, ProjectedModel


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str


class Customer(BaseModel):
    id: int
    name: str
    email: str
    address: Address


class Order(BaseModel):
    order_id: int
    customer: Customer
    status: str = 'pending'
    notes: str = ''


class AddressBrief(ProjectedModel[Address]):
    city: Projected
    state: Projected

class CustomerBrief(ProjectedModel[Customer]):
    name: Projected
    address: AddressBrief

class OrderSummary(ProjectedModel[Order]):
    order_id: Projected
    customer: CustomerBrief
    status: Projected

data = {
    'order_id': 1001,
    'customer': {
        'name': 'Alice Smith',
        'address': {'city': 'Portland', 'state': 'OR'},
    },
    'status': 'shipped',
}

summary = OrderSummary.model_validate(data)
print(summary.model_dump())
"""
{'order_id': 1001, 'customer': {'name': 'Alice Smith', 'address': {'city': 'Portland', 'state': 'OR'}}, 'status': 'shipped'}
"""
```

## Configuration and Settings

Application config objects often contain secrets. A projection lets you derive a safe-to-expose
view that structurally *cannot* leak sensitive values.

```python
from pydantic import BaseModel, Field, Projected, ProjectedModel


class AppConfig(BaseModel):
    app_name: str = 'my-service'
    debug: bool = False
    database_url: str = Field(description='Postgres connection string')
    secret_key: str = Field(min_length=32)
    allowed_hosts: list[str] = ['*']
    max_connections: int = Field(default=100, ge=1)


class PublicConfig(ProjectedModel[AppConfig]):
    app_name: Projected
    debug: Projected
    allowed_hosts: Projected
    max_connections: Projected

full = AppConfig(
    database_url='postgresql://user:pass@db:5432/app',
    secret_key='super-secret-key-that-is-at-least-32-chars!',
)
public = PublicConfig(
    app_name=full.app_name,
    debug=full.debug,
    allowed_hosts=full.allowed_hosts,
    max_connections=full.max_connections,
)

print(public.model_dump())
#> {'app_name': 'my-service', 'debug': False, 'allowed_hosts': ['*'], 'max_connections': 100}
```

## Form Handling

When a web form only collects a subset of a model's fields, a projection gives you targeted
validation without a throwaway schema.

```python
from pydantic import BaseModel, Field, Projected, ProjectedModel, ValidationError


class UserProfile(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    display_name: str = Field(max_length=64)
    bio: str = Field(default='', max_length=500)
    website: str = ''
    avatar_url: str = ''
    email_verified: bool = False


class ProfileForm(ProjectedModel[UserProfile]):
    display_name: Projected
    bio: Projected
    website: Projected

# Valid form submission
form_data = {'display_name': 'Alice', 'bio': 'Engineer & OSS contributor.', 'website': 'https://alice.dev'}
form = ProfileForm.model_validate(form_data)
print(form.model_dump())
#> {'display_name': 'Alice', 'bio': 'Engineer & OSS contributor.', 'website': 'https://alice.dev'}

# Invalid submission — max_length=64 on display_name is preserved from UserProfile
bad_data = {'display_name': 'A' * 100, 'bio': 'hi'}
try:
    ProfileForm.model_validate(bad_data)
except ValidationError as e:
    print(e.error_count())
    #> 1
```
