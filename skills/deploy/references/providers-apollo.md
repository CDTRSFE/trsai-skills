# Apollo Provider

For detailed Apollo-specific behavior, use the existing `apollo-deploy` skill.

Apollo capability profile:

```text
build: true
extractImage: true
syncImage: true
discoverConfig: true
```

Follow the Apollo skill's API-first rules for authentication, system selection, pipeline discovery, build start, log polling, image extraction, app discovery, `deployByImage`, and `getStatus`.

When `provider` is `apollo`, the existing Apollo skill remains the source of truth for:

- known Apollo environment mapping
- API login and local secret loading details
- Apollo endpoint paths
- current-build correlation rules
- `appId` discovery and writeback
- Apollo success and failure reporting

Do not duplicate or reinterpret Apollo endpoint details here. If an Apollo rule changes, update `apollo-deploy` first, then keep this provider reference as a router.
