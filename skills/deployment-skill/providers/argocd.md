# ArgoCD Provider

ArgoCD deployment is not supported yet.

If `deploy.json` has `"provider": "argocd"` or the user selects ArgoCD, stop and say this provider still needs team rules before it can safely mutate external deployment state.

Do not infer ArgoCD apps, clusters, namespaces, sync policies, or credentials from local project names.
