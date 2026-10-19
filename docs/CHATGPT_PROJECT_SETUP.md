# ChatGPT project and session organization

## Recommended structure

Create one ChatGPT project named **Nicks Multisport Lab** and place the current
coordination conversation there. Use it for the platform roadmap, source
decisions, integration questions and reviews of Codex results.

Start with one new Codex implementation owner connected to
[`NickNicky19/Nicks-multisport-lab-project`](https://github.com/NickNicky19/Nicks-multisport-lab-project).
That owner can delegate bounded implementation, research and verification work to
agents using the repository's shared protocol. A separate ChatGPT conversation
for every NBA category is unnecessary.

| Conversation or project | Responsibility | When to create or use it |
| --- | --- | --- |
| This multisport coordination chat | Product scope, shared architecture, integration decisions and result review | Keep as the primary coordination conversation |
| NBA research chat within the multisport project | Detailed NBA experiments, diagnostics and category findings | Add when specialist discussion would otherwise crowd the coordination chat |
| Later sport research chats within the multisport project | The active sport's data, contracts, methods and evaluation | Add when that sport's work actually starts |
| Existing NFL project and sessions | Existing NFL implementation and research | Keep separate and unchanged |
| Existing MLB project and sessions | Existing MLB model and its own evidence | Keep separate; later share versioned outputs through an agreed import interface |
| New Codex implementation session | Integrated repository changes, tests, model runs and website implementation | One owner initially, with coordinated agents as needed |

Do not open a separate project and implementation writer for every future sport
before the shared platform exists. Add specialist conversations when they have a
specific question, bounded task and agreed handoff target.

## Continuity that can be checked

A ChatGPT project is an organizational aid. Do not assume every conversation has
automatically read every other transcript, a newly changed repository file or the
latest Codex result. A source link in a conversation is not a live repository
synchronization mechanism.

Use these durable repository documents:

- [`PROJECT_CONTEXT.md`](../PROJECT_CONTEXT.md): accepted scope, project boundaries and operating constraints.
- [`HANDOFF_STATUS.md`](../HANDOFF_STATUS.md): current observed checkpoint, exact commits, remaining work and evidence limitations.
- [`AGENTS.md`](../AGENTS.md): implementation and scientific working instructions.
- [`CODEX_START_HERE.txt`](../CODEX_START_HERE.txt): the detailed implementation kickoff.

When starting a fresh conversation, provide the repository URL, relevant current
commit, current handoff and the specific task. Ask it to verify those facts before
making claims about current code or performance. If repository access is missing,
provide the relevant files or report instead of asking it to infer their contents.

A specialist chat should return a focused research note or review containing its
assumptions, evidence, recommendation and unresolved questions. The integration
owner incorporates accepted changes and records the outcome. Chat titles and
separate conversations do not establish independent writer ownership by
themselves.

## Copy-ready ChatGPT project instructions

Paste the following into the new ChatGPT project's instructions:

```text
This is Nick's independent multisport player-prop research and paper-ticket
project. Canonical repository:
https://github.com/NickNicky19/Nicks-multisport-lab-project

Use this project's coordination conversation for shared decisions and reviews.
Consult the current repository PROJECT_CONTEXT.md, HANDOFF_STATUS.md and AGENTS.md
before continuing work. Verify the actual commit and evidence; do not assume
automatic access to other chats or live repository changes. Nick's latest explicit
instructions govern.

NBA is first. Full required scope: points; PRA; rebounds; three-pointers made;
assists; rebounds + assists; points + rebounds; turnovers; triple-double;
double-double; blocks; steals; blocks + steals. Points + assists is optional.
Every later sport has a comprehensive-category goal. The first controlled REB
experiment sets an improvement sequence, not a one-category limit.

Use a shared participation/minutes/role foundation and coherent joint outcomes.
Keep chronological evaluation, correctly timed inputs, category-specific evidence
and explicit uncertainty. Synthetic tests, proposed methods and source metadata
are not trained-model results, validated feeds or proof of profitability.

The paper builder supports 2–6 legs, with six preferred only when the complete
ticket qualifies. Keep OVER_ONLY, UNDER_ONLY, MIXED and NO_ACTION. Use exact
contracts, actual payout/settlement terms, a common ticket decision time and
supported joint probabilities. Do not force six legs or invent missing prices.

Use no new paid services, trials, subscriptions, signups or API keys by default.
Use permitted public data, existing authorized access or supplied files. Keep
unaffected statistical work moving when a live-price source remains unresolved.

NFL stays in its existing project and sessions: do not change its repository,
contact its writer or trigger its workflows. Existing MLB work remains separate;
import versioned outputs later. Inspect prior NBA work before duplicating it.

Use one Codex integration owner initially, with coordinated agents and bounded
specialist research chats. Do not create duplicate workbooks, repositories,
implementation writers or recurring schedulers. Report what changed, how it was
checked, exact commits, remaining uncertainty and the next concrete task.
```

## First message for a later specialist research chat

```text
This chat supports the existing Nicks Multisport Lab project. Read the current
PROJECT_CONTEXT.md, HANDOFF_STATUS.md and the relevant sport specification in
https://github.com/NickNicky19/Nicks-multisport-lab-project.

Verify the repository revision and current evidence before proceeding. Work on
this bounded question: [insert the specific question]. Return findings and an
implementation recommendation to the integration owner. Do not start a competing
writer or scheduler, modify the external NFL/MLB projects, or repeat completed
audits unless a concrete new issue requires it.
```

Replace the bracketed question with an actual task when the specialist chat is
needed. There is no need to create all future sport chats now.
