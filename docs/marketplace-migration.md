# Marketplace migration

The repository is now `DmitriyYukhanov/agent-plugins`. Its marketplace ID remains
`dmitriy-claude-plugins`, so existing installs keep their
`<plugin>@dmitriy-claude-plugins` keys.

New installs use the new repository address:

```sh
claude plugin marketplace add DmitriyYukhanov/agent-plugins
codex plugin marketplace add DmitriyYukhanov/agent-plugins
```

The repository address and marketplace ID serve different purposes. The address
locates the catalog; its top-level `name` identifies installed plugins and their
settings. Keeping that name avoids an uninstall and reinstall migration.

Claude Code's [`renames` map](https://code.claude.com/docs/en/plugins/host-marketplace#rename-or-remove-a-plugin)
migrates plugin names within a marketplace. It does not document an alias for a
marketplace name. Codex's documented marketplace commands are `add`, `list`,
`upgrade`, and `remove`; they do not include a rename command. See
[Package your plugin](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli).

## Phase 1: update the source, keep the ID

For each installation, identify its configuration root before editing anything.
Claude Code profiles can use different `CLAUDE_CONFIG_DIR` values; Codex uses
`CODEX_HOME` when set. A profile name or an existing cache directory does not
prove which configuration a running client uses.

1. Back up each file you will edit to a private location. Record installed plugin
   names, versions, scopes, enabled flags, marketplace refs, and update settings.
   Keep credentials and account files outside the migration.
2. Change only the source address for `dmitriy-claude-plugins`.
3. Parse the edited files and compare them with the backups. Verify that plugin
   keys, enabled flags, installed versions, scopes, and cache paths stayed the same.
4. Refresh the marketplace through the host's command when you are ready to fetch
   its latest catalog. Check installed state again after the refresh.

For Codex, the existing registration in `config.toml` has this form:

```toml
[marketplaces.dmitriy-claude-plugins]
source_type = "git"
source = "git@github.com:DmitriyYukhanov/agent-plugins.git"
ref = "main"
```

Preserve the installation's existing protocol and ref when they work. If a
native refresh fails because the existing SSH transport cannot authenticate,
back up `config.toml` again and change only this registration's source to
`https://github.com/DmitriyYukhanov/agent-plugins.git`. Retry the same refresh.
Keep global Git transport settings, credentials, and account selection unchanged.
Leave every `[plugins."<plugin>@dmitriy-claude-plugins"]` block unchanged,
including plugins whose `enabled` flag is `false`.

For Claude Code, inspect the existing entry in
`<configuration-root>/plugins/known_marketplaces.json`. A GitHub registration
uses a nested source object:

```json
{
  "source": {
    "source": "github",
    "repo": "DmitriyYukhanov/agent-plugins"
  }
}
```

Change `source.repo` on the existing `dmitriy-claude-plugins` entry. Keep its other
fields, including `installLocation` and the update preference. If settings also
declare this marketplace in `extraKnownMarketplaces`, update that declaration's
source too. Leave `enabledPlugins`, `pluginConfigs`, and
`installed_plugins.json` unchanged. These are local storage files; inspect the
installed host's schema before editing them.

If the registered marketplace cache is a Git checkout of this repository, update
its `origin` after backing up `.git/config`. Check the current origin first and
preserve its protocol. A copied marketplace directory may have no `.git`; it
needs no Git remote change.

```sh
git -C <marketplace-checkout> remote set-url origin git@github.com:DmitriyYukhanov/agent-plugins.git
```

If that checkout's SSH origin prevents the native refresh, back up `.git/config`
and set only its origin to the HTTPS address before retrying. A successful native
refresh needs no transport change.

### Repair a cache outside its profile

Claude Code can reject a registered `installLocation` with a `corrupted
installLocation` error when the path is outside that profile's
`plugins/marketplaces/` directory. A shared seed copied from another profile can
trigger this check even when its catalog files are present.

Back up the profile's `settings.json`, `plugins/installed_plugins.json`, and
`plugins/known_marketplaces.json`. Change only the affected marketplace's
`installLocation` to
`<configuration-root>/plugins/marketplaces/dmitriy-claude-plugins`. Check that the
resolved path is inside that profile's marketplace directory and does not
overwrite another checkout. Then run the native refresh against that profile:

```sh
claude plugin marketplace update dmitriy-claude-plugins --json
```

In the tested repair, this command created the missing cache as a Git checkout
and refreshed its catalog. Parse the resulting metadata and compare it with the
backups: settings and installed plugin records should remain equal, while the
affected registration can have the new cache path and refresh metadata. Verify
that its source and auto-update preference are unchanged and that other
marketplace registrations are equal to their backups. Leave the shared seed and
its owner scripts unchanged.

Avoid the error message's suggested marketplace removal when preserving existing
installs. That command can uninstall plugins and delete their saved state. The
cache path repair does not require it.

### Verify the registration

For validation and a deliberate catalog refresh:

```sh
codex plugin marketplace list --json
codex plugin list --marketplace dmitriy-claude-plugins --json
codex plugin marketplace upgrade dmitriy-claude-plugins

claude plugin marketplace list --json
claude plugin list --json
claude plugin marketplace update dmitriy-claude-plugins
```

Run each command against the intended configuration root. A refresh can fetch
new catalog contents; it is separate from checking local files.

Claude Code's marketplace auto-update also updates installed plugins after a
session starts. To enable it, use `/plugin`, open Marketplaces, select
`dmitriy-claude-plugins`, and choose Enable auto-update. The running session keeps
the versions it already loaded until plugins reload. See
[Keep plugins updated](https://code.claude.com/docs/en/discover-plugins#keep-plugins-updated).
Codex's packaging documentation describes refresh through `marketplace upgrade`
but does not document a matching per-marketplace `autoUpdate` setting; do not add
one to its TOML configuration.

To roll back the source change, restore the edited files from their backups.
Do not restore a whole configuration root over newer sessions or account state.

## Phase 2: optional marketplace ID change

Changing the marketplace ID to `dmitriy-agent-plugins` is a separate migration.
It requires new install keys, cache locations, and settings references. Keep
Phase 1's stable ID until a migration has been tested on every supported host.

Before that migration, export an inventory for each configuration root and every
user, project, local, or managed scope that references the old ID. Include
disabled plugins, pinned versions, plugin options, and persistent data. Back up
those files privately. Install and verify the corresponding plugins under the
new ID, then restore each scope's enabled state and options. Installing from a
new catalog can select newer versions, so verify version parity explicitly.

Do not start by removing the old marketplace. Claude Code's
[`marketplace remove`](https://code.claude.com/docs/en/plugins/cli-reference#plugin-marketplace-remove)
can uninstall all its plugins and delete their saved options, secrets, and data.
Retire the old registration only after the new installs and any data migration
are verified and those deletions are acceptable. Managed settings require their
administrator to update the references.
