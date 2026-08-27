---
title: Designing for voice
description: What changes when the output is spoken, the caller can interrupt, and the screen is right there. The durable half of the problem.
---

Getting a call working is a week. Getting one people use twice is the rest of the
work, and almost none of it is about the API. Speech has no scrollback. A caller
can interrupt you mid-word. The screen is right there and it holds detail the ear
cannot. These pages are the arguments, written from running production voice
agents rather than from first principles.

## The two channels

**Voice points. The screen holds.** Speech is linear, transient and interruptible
— it is good at direction, acknowledgement and one number at a time. The screen
is durable and scannable — it is good at lists, totals, forms and anything the
caller would otherwise have to remember. A number the caller must hold in their
head belongs on the screen.

The mechanism for the second channel is [actions](/build/brain/actions/); this
section is about what to send and when.

## The pages

| | |
|---|---|
| [Voice points, the screen holds](/design/speech-vs-screen/) | What belongs in the ear and what belongs on the page. |
| [The turn budget](/design/turn-budget/) | How long a unit may be, and what the caller does when it is longer. |
| [Interruption and heard truth](/design/interruption-and-heard-truth/) | Barge-in, and why history holds what was heard. |
| [Misunderstanding and reversal](/design/misunderstanding-and-reversal/) | Recovering when the agent got it wrong, without starting over. |
| [Parallel workstreams](/design/parallel-workstreams/) | Work that outlives the turn that started it. |
| [Prompt design for voice](/design/prompt-design/) | A prompt written for an ear, not a text box. |
| [Tool design for voice](/design/tool-design/) | Tools whose latency the caller can hear. |

## When you are done here

You have an application worth putting in front of people. Keeping it working is
[Operate](/operate/).
