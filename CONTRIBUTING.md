# Contributing Guidelines

Thank you for your interest in contributing to our project! 
Please follow these guidelines to help maintain consistency and streamline the development process.

## General Rules

1. **Issue Creation**: Create issues for everything you won't start working on immediately.
2. **Project Assignment**: Assign issues to either the backlog or planning projects.
3. **Labeling**: Use labels to categorize issues appropriately.
4. **Branch Creation**: Use the GitHub "create branch" button to create branches directly from issues.
5. **Semantic Commits**: Adhere to the semantic commit format for clear and descriptive commits.
6. **Issue-less Branches**: You may use branches without associated issues for small tasks and fixes.

## Branch Names

- Follow the default GitHub suggested format: issue number prefixed, hyphen-separated, and lowercase, e.g., `1234-fix-bug`.
- Avoid using prefixes like `feature/`, `bugfix/`, etc.
- Ensure names are short yet descriptive and use present tense.
- For branches without issues, use descriptive names, e.g., `fix-bug-in-auth`.

## Commits

Commit messages should be formatted as follows:

```
<type>(<scope>): <short summary>
  │       │             │
  │       │             └─⫸ Summary in present tense. Not capitalized. No period at the end.
  │       │
  │       └─⫸ Commit Scope: setting|browser|editor|auth|inbox|preview|activities|....
  │
  └─⫸ Commit Type: build|ci|docs|feat|fix|perf|refactor|test
```

The `<type>` and `<summary>` fields are mandatory, the `(<scope>)` field is optional.

- use imperative, present tense: “change” not “changed” nor “changes”
- don't capitalize first letter
- no dot (.) at the end

### Examples

- `feat(settings): add settings copy`
- `fix(auth): fix session expiration`
- `feat: add video preview endpoint`

## Labels

Use the following labels to categorize issues:

- `bug` — For marking bugs.
- `enhancement` — For improvements to existing features.
- `feature` — For new features.
- `maintenance` — For general maintenance tasks.
- `wontfix` — For issues that will not be addressed (issues only).
- `epic` — For large features or tasks that encompass multiple issues (issues only).

Your contributions are invaluable to us. 
Following these guidelines helps us manage the project effectively and ensures that your contributions are integrated smoothly. 

Thank you for collaborating with us!
