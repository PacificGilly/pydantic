??? api "API Documentation"
    [`pydantic.projected_model.ProjectedModel`][pydantic.projected_model.ProjectedModel]<br>
    [`pydantic.projected_model.Projected`][pydantic.projected_model.Projected]<br>

Projected models provide a declarative way to create **subset views** of existing Pydantic models —
selecting only the fields you need while preserving their type annotations, validators, defaults,
constraints, and other field metadata from the source model.

This is useful for API response shaping, DTO / read-model patterns, and GraphQL-style field
selection. Instead of manually redefining types and constraints on a second model, you point at
the source and say *"I want these fields"*.

The resulting class **is** a standard [`BaseModel`][pydantic.main.BaseModel] — it supports full
validation, serialisation, JSON Schema generation, and everything else you would expect.

## Basic Usage

To create a projection you need two things:

1. A source model — any [`BaseModel`][pydantic.main.BaseModel] subclass.
2. A projection class that inherits from `ProjectedModel[SourceModel]` and annotates each desired
   field with the [`Projected`][pydantic.projected_model.Projected] sentinel type.

```python {group="basic"}
from pydantic import BaseModel, Field, Projected, ProjectedModel


class User(BaseModel):
    id: int
    name: str
    email: str
    age: int = Field(ge=0)
    bio: str = ''

class UserSummary(ProjectedModel[User]):
    id: Projected
    name: Projected
```

```python {group="basic"}
user = UserSummary(id=1, name='Alice')
print(user.model_dump())
#> {'id': 1, 'name': 'Alice'}
print(isinstance(user, BaseModel))
#> True
```

Only the fields you annotate in the projection are included — `email`, `age`, and `bio` are
not part of `UserSummary` at all.

## Field Metadata Preservation

When you annotate a field with `Projected`, every piece of metadata from the source field is
deep-copied into the projection: the type annotation, the default value, `Field` constraints
(`gt`, `ge`, `max_length`, …), the `description`, `alias`, and so on.

```python
from pydantic import BaseModel, Field, Projected, ProjectedModel, ValidationError


class Product(BaseModel):
    sku: str
    price: float = Field(gt=0, description='Retail price in USD')
    currency: str = 'USD'

class ProductPrice(ProjectedModel[Product]):
    price: Projected
    currency: Projected

item = ProductPrice(price=9.99)  # currency defaults to 'USD'
print(item.model_dump())
#> {'price': 9.99, 'currency': 'USD'}

try:
    ProductPrice(price=-5)
except ValidationError as e:
    print(e.error_count())
    #> 1
```

## Nested Projections

If your source model contains a field whose type is another `BaseModel`, you can project that
nested model too — annotate the field with a `ProjectedModel` subclass targeting the nested source:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class Address(BaseModel):
    street: str
    city: str
    zip_code: str
    country: str = 'US'

class Customer(BaseModel):
    id: int
    name: str
    address: Address

class AddressBrief(ProjectedModel[Address]):
    city: Projected
    country: Projected

class CustomerBrief(ProjectedModel[Customer]):
    name: Projected
    address: AddressBrief

brief = CustomerBrief(name='Bob', address={'city': 'Springfield', 'country': 'US'})
print(brief.model_dump())
#> {'name': 'Bob', 'address': {'city': 'Springfield', 'country': 'US'}}
```

## Deeply Nested Projections

The pattern composes to arbitrary depth — just stack projections. Here `Company` contains
an `Address` which contains a `Street`, and each level is projected independently:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class Street(BaseModel):
    name: str
    number: int

class Address(BaseModel):
    street: Street
    city: str

class Company(BaseModel):
    title: str
    address: Address

class StreetView(ProjectedModel[Street]):
    name: Projected

class AddressView(ProjectedModel[Address]):
    street: StreetView
    city: Projected

class CompanyView(ProjectedModel[Company]):
    title: Projected
    address: AddressView

print(CompanyView(title='Acme', address={'street': {'name': 'Main St'}, 'city': 'Portland'}).model_dump())
#> {'title': 'Acme', 'address': {'street': {'name': 'Main St'}, 'city': 'Portland'}}
```

## Using Plain `BaseModel` for Nested Fields

You don't have to use a `ProjectedModel` for nested fields — any `BaseModel` subclass works.
This is handy when you want to keep **all** fields from the nested model:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class Address(BaseModel):
    street: str
    city: str
    zip_code: str

class Customer(BaseModel):
    id: int
    name: str
    address: Address

class CustomerView(ProjectedModel[Customer]):
    name: Projected
    address: Address  # plain BaseModel — keeps every Address field

print(CustomerView(name='Alice', address={'street': '1 Elm', 'city': 'Portland', 'zip_code': '97201'}).model_dump())
#> {'name': 'Alice', 'address': {'street': '1 Elm', 'city': 'Portland', 'zip_code': '97201'}}
```

## Multiple Projections from the Same Source

You can create as many independent projections of the same source model as you like:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class User(BaseModel):
    id: int
    name: str
    email: str
    age: int
    bio: str = ''

class UserPublic(ProjectedModel[User]):
    id: Projected
    name: Projected
    bio: Projected

class UserContact(ProjectedModel[User]):
    name: Projected
    email: Projected

print(list(UserPublic.model_fields.keys()))
#> ['id', 'name', 'bio']
print(list(UserContact.model_fields.keys()))
#> ['name', 'email']
```

## Validation

Projected models are full `BaseModel` subclasses, so all of Pydantic's validation machinery
applies — constraints from the source model are enforced:

```python
from pydantic import BaseModel, Field, Projected, ProjectedModel, ValidationError


class Item(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(ge=0)

class ItemView(ProjectedModel[Item]):
    name: Projected
    quantity: Projected

try:
    ItemView(name='', quantity=-1)
except ValidationError as e:
    print(e.error_count())
    #> 2
```

## JSON Schema

Calling `model_json_schema()` returns a schema containing only the projected fields:

```python
from pydantic import BaseModel, Field, Projected, ProjectedModel
 

class User(BaseModel):
    id: int
    name: str = Field(description='Full name')
    email: str

class UserPublic(ProjectedModel[User]):
    id: Projected
    name: Projected

schema = UserPublic.model_json_schema()
print(schema['title'])
#> UserPublic
print(sorted(schema['properties']))
#> ['id', 'name']
print(schema['properties']['name']['description'])
#> Full name
```

## Serialization

`model_dump()`, `model_dump_json()`, and the corresponding `model_validate` /
`model_validate_json` round-trip methods all work as expected:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class User(BaseModel):
    id: int
    name: str
    email: str

class UserSummary(ProjectedModel[User]):
    id: Projected
    name: Projected

user = UserSummary(id=42, name='Alice')
print(user.model_dump())
#> {'id': 42, 'name': 'Alice'}
print(user.model_dump_json())
#> {"id":42,"name":"Alice"}
print(UserSummary.model_validate_json('{"id":42,"name":"Alice"}'))
#> id=42 name='Alice'
```

## Error Handling

`ProjectedModel` performs validation **at class-creation time** to catch configuration mistakes
as early as possible. There are three error cases:

### Field not found in source

If you reference a field that does not exist on the source, a `ValueError` is raised:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class User(BaseModel):
    id: int
    name: str

try:
    class BadProjection(ProjectedModel[User]):
        nickname: Projected  # does not exist on User
except ValueError as e:
    print(e)
    #> Scalar field `nickname` specified in `BadProjection` not found in its source model `User`
```

### Invalid annotation type

Only `Projected` and `BaseModel` subclasses are valid field annotations. Anything else raises `TypeError`:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class User(BaseModel):
    id: int
    name: str

try:
    class BadAnnotation(ProjectedModel[User]):
        name: str  # plain type — not allowed
except TypeError as e:
    print(e)
    #> Field `name` on `BadAnnotation` must be `Projected` or a Projection subclass, got `<class 'str'>`
```

### Mismatched nested projection source

A nested `ProjectedModel` whose source doesn't match the parent field type raises `TypeError`:

```python
from pydantic import BaseModel, Projected, ProjectedModel

class Address(BaseModel):
    city: str

class Company(BaseModel):
    name: str

class Customer(BaseModel):
    id: int
    address: Address

class CompanyView(ProjectedModel[Company]):
    name: Projected

try:
    class BadNested(ProjectedModel[Customer]):
        address: CompanyView  # CompanyView projects Company, not Address
except TypeError as e:
    print(e)
    #> Nested projection `CompanyView` projects `Company`, but `Customer.address` is of type `Address`
```

## Comparison with Other Patterns

| Approach | Pros | Cons |
|---|---|---|
| `ProjectedModel` | Declarative, preserves metadata, static types, JSON schema | One new concept |
| Separate `BaseModel` | Simple, explicit | Duplicates field definitions — easy to drift |
| `create_model()` | Flexible, no class boilerplate | No static type checking, harder to read |
| `model_dump(include=...)` | Zero extra classes | Runtime-only, no schema, returns a `dict` |

!!! note
    `ProjectedModel` is the best fit when you want a **typed, schema-aware** subset of an existing
    model that stays in sync with the source automatically. If you only need to filter fields at
    serialisation time and don't need a separate schema, `model_dump(include=...)` may be simpler.