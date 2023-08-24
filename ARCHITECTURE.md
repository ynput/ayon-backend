# Architecture

The Ayon Server is a Python package, with a FastAPI based API, for the Ayon PostgresSQL database.

```
.
├── addons - Third party Addons.
├── api - The FastAPI REST implementation for `ayon_server`.
├── ayon_server - Actual server logic.
├── demogen - Demo generator, creates random data in the Database.
├── linker - Adds realtions to the Database.
├── schemas - SQL Table Schemas.
├── setup - Setup of the required data in the Database.
└── static - GraphQL HTML explorer.
```

## Ayon Server

A Python package that will replace the current MongoDB implementation with a PostreSQL one.

```
ayon_server/
├── access - Permissions, access groups... i.e. Admin, Project Manager, etc.
├── addons - Base classes for Addon's creation and Addon loading/importing logic.
├── api - Python interface for the different modules.
├── auth - Authentication via password or SSO and Session handling.
├── entities - Definition of the `BaseEntity` and the current existing entities i.e. Project, Folder, Task, etc. With all their available attributes.
├── events - Base definition for events based on specific actions.
├── graphql - GraphQL interface.
├── helpers - Loose scripts.
├── lib - Libraries for re-use within the package, i.e. Postgres methods.
├── settings - Ayon settings, i.e. Anatomy definitions.
├── background.py - Class to create async tasks.
├── config.py - Ayon server configuration.
├── exceptions.py - Ayon Specific Exceptions.
├── logs.py - Merge the different async logs into one.
├── types.py - Types and Constants to be used across the pacakge.
└── utils.py - JSON, dicts, etc. helpers.
```


