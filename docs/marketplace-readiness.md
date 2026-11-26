# Snippo 1.0.0 release gates

WP-02 prepares a local VSIX. The publisher account is managed separately in the Marketplace under `dineshkaarthik`, with intended display name **Dinesh Kaarthik**. Confirm the displayed publisher name in the Marketplace account before a future upload.

| Area | Observed behavior and release action |
| --- | --- |
| Email identity | Verification, recovery and legacy account holds are implemented. The hosted private-test configuration must be switched using the [rollout guide](public-authentication.md), then verified with real delivery and a legacy-owner review before opening registration. |
| Signup abuse | Flask rate-limits signup, resend and recovery. Direct provider requests bypass Flask. Apply and verify Supabase rate limits and Gmail SMTP capacity before opening registration. Keep signup restricted if distributed abuse can exhaust the email budget. |
| Sessions | The desktop extension uses S256 PKCE, a random state, validated callback targets, SecretStorage, and refresh-token renewal. Flask validates API bearer identity at Supabase and tracks revoked desktop sessions. Desktop sign-out can clear local tokens while an outage prevents server revocation. Verify renewal and revocation on a real device before release. |
| Isolation | Flask queries snippets by authenticated owner and the database enforces row-level security with restricted grants. Keep the dedicated database role. Complete a hosted two-account test after deploying the matching backend. |
| Privacy and deletion | Auth and snippet data are transmitted to the hosted services. Web users can delete snippets. There is no self-service account deletion and no verified retention or deletion policy. Publish an accurate privacy notice and a private support contact. Establish a verified account-deletion process that accounts for owned snippets and backups. The snippet ownership foreign key restricts deletion of an account while snippets remain. |
| Hosting | The hosted origin must be reachable and serve the updated callback. Supabase Free has finite database, Auth, and transfer allowances and can pause inactive projects. Vercel Hobby is restricted to personal, non-commercial use. Confirm plan eligibility and capacity for the planned distribution. |
| Marketplace | Check the current publisher agreement, listing and packaging rules, and applicable privacy obligations before manual upload. Confirm support details. Custom artwork can be added separately once approved. |

References: [VS Code packaging and publishing](https://code.visualstudio.com/api/working-with-extensions/publishing-extension), [Visual Studio Marketplace Publisher Agreement](https://cdn.vsassets.io/v/M187_20210610.3/_content/Visual-Studio-Marketplace-Publisher-Agreement.pdf), [Supabase Auth rate limits](https://supabase.com/docs/guides/auth/rate-limits), [Supabase SMTP](https://supabase.com/docs/guides/auth/auth-smtp), [Supabase pricing](https://supabase.com/pricing), and [Vercel Hobby](https://vercel.com/docs/plans/hobby).

## Build and install

From the repository root on a system with Node.js 24 and a compatible VS Code Desktop installation:

```sh
cd vscode_extension
npm ci
npm test
npm run package
code --install-extension ./snippo-1.0.0.vsix
```

Or use **Extensions: Install from VSIX...**. Review `npm audit` for build-tool exposure and `npm audit --omit=dev` for distributable dependencies.

## Manual integration and acceptance

1. After separate authorization, deploy the backend with the Snippo callback template. Verify the registered HTTPS callback is still `/oauth/vscode/callback` on the existing origin. Confirm both **Open VS Code** and **Open VS Code Insiders** point to the new extension.
2. Disable or uninstall the old extension before installing Snippo. Sign in from the browser. The old extension's stored tokens do not transfer.
3. Check the signed-in status, own starter and custom snippets, name/code search, and insertion into an editor.
4. Close and reopen VS Code. Confirm the saved session works and verify token renewal after access-token expiry.
5. Sign in with a second test account and confirm it sees only its own snippets. Test manual sign-out and web revocation across devices.
6. Resolve the release gates above before the publisher uploads a VSIX. An actual Marketplace upload is a separate operation.
