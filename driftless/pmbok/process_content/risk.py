"""Plain-language content for the Risk Management processes (11.1-11.7),
``KnowledgeArea.RISK``.

Risk management is deciding how you will handle uncertainty, finding what
could go wrong (or go especially right), sizing it, deciding what to do
about it, actually doing that, and then watching for what changes.
"""

from __future__ import annotations

from driftless.pmbok.process_content import ProcessContent

AREA = "risk"

CONTENT: dict[str, ProcessContent] = {
    "11.1": ProcessContent(
        plain_summary="Decide, up front, how you will find, size, and respond to risk.",
        why_bother=(
            "Without an agreed approach, one person's minor concern and another's serious "
            "threat get treated the same way, and the genuine threat can slip through."
        ),
        done_when="A risk management approach is written down, including how risks will be scored.",
        first_time_tip=(
            "Agree on the scoring scale before anyone logs a risk. Comparing risks scored "
            "on two different scales tells you nothing useful."
        ),
        worked_example=(
            "A volunteer committee is running a one-day outdoor music festival in a town "
            "park. Before anyone lists a single worry, the committee agrees how this will "
            "work: risks go in a shared register, each gets a likelihood and an impact rated "
            "low, medium or high against a scale written down in advance, and anything high "
            "on both goes to the chair for a decision rather than to whoever spotted it."
        ),
        pitfalls=(
            'Letting each member score against a private sense of "serious", so two risks '
            "both rated high mean quite different things.",
            "Writing the approach after the first risks are already logged, then having to "
            "rescore all of them.",
            "Making the approach so heavy that volunteers stop logging risks at all.",
        ),
    ),
    "11.2": ProcessContent(
        plain_summary="Find and write down anything that could help or hurt the project.",
        why_bother=(
            "A risk nobody wrote down cannot be planned for, and the first time anyone "
            "reacts to it is after it has already happened."
        ),
        done_when="Identified risks are logged in the risk register with enough detail to assess later.",
        first_time_tip=(
            "Ask the team for risks individually before a group session. People often "
            "raise a genuine concern alone that they would hold back from voicing in a group."
        ),
        worked_example=(
            "The committee asks each volunteer privately what worries them, then meets to "
            "pool the answers. The list includes a thunderstorm on the day, the headline act "
            "cancelling, the portable toilets arriving late, and one nobody had said out loud "
            "in a group — that the only person who knows the electrical setup is away the "
            "week before."
        ),
        pitfalls=(
            "Running only a group session, so the concern that makes someone look "
            "unprepared never gets raised.",
            'Logging a risk as a single word like "weather", which is too vague to plan a '
            "response against later.",
            "Stopping at the obvious risks and never adding to the list as the date gets closer.",
        ),
    ),
    "11.3": ProcessContent(
        plain_summary="Rank the logged risks by how likely and how serious each one is.",
        why_bother=(
            "Treating every risk on the register as equally urgent spreads limited attention "
            "too thin to matter, and the genuinely dangerous ones get lost in the noise."
        ),
        done_when="Every logged risk has a likelihood and impact rating and is ranked by priority.",
        first_time_tip=(
            "Re-rank the whole register on a fixed schedule, not just when a new risk "
            "appears. A risk's priority can shift even when nothing new has happened."
        ),
        worked_example=(
            "Using the scale agreed up front, the committee rates what it logged. A "
            "thunderstorm is both likely enough and damaging enough to land high on each, "
            "the headline act cancelling is unlikely but severe, and the toilets arriving "
            "late is likely but easy to absorb. The register is reordered so the storm and "
            "the cancellation sit at the top."
        ),
        pitfalls=(
            "Rating everything medium to avoid an argument, which leaves the register in no "
            "useful order at all.",
            "Scoring once at kickoff and never rescoring as the forecast and the bookings firm up.",
            "Mistaking how loudly someone raised a risk for how serious it actually is.",
        ),
    ),
    "11.4": ProcessContent(
        plain_summary="Run the numbers on how the top risks could affect cost and schedule.",
        why_bother=(
            "A ranked list tells you order but not scale; this puts an actual number on how "
            "much schedule or budget cushion the top risks genuinely justify."
        ),
        done_when="A numeric analysis of the top risks' combined effect on cost and schedule exists.",
        first_time_tip=(
            "Reserve this deeper analysis for the highest-ranked risks only. Running it on "
            "every minor risk on the register costs more than it is worth."
        ),
        worked_example=(
            "For the two risks at the top, the committee works out what they would really "
            "cost. A washed-out day means refunding every ticket and still paying the stage "
            "hire, about three quarters of the budget, while a headline cancellation means "
            "paying a replacement act and selling fewer tickets. Sized and added together, "
            "they show the committee how large a contingency fund the ranked list alone "
            "never justified."
        ),
        pitfalls=(
            "Running the numbers on every entry in the register, which costs more volunteer "
            "time than the answer is worth.",
            "Presenting one figure as certain when it rests on a rough guess about ticket sales.",
            "Sizing the risks carefully and then setting the contingency fund by gut feel anyway.",
        ),
    ),
    "11.5": ProcessContent(
        plain_summary="Decide, for each significant risk, what you will actually do about it.",
        why_bother=(
            "A risk that is identified and scored but has no plan attached is still just a "
            "worry; this is the step that turns it into an action someone owns."
        ),
        done_when="Every significant risk has an assigned response strategy and an owner.",
        first_time_tip=(
            "Name a single owner for each response, not a team. A response owned by "
            "everyone tends to be actioned by no one."
        ),
        worked_example=(
            "For the storm the committee books a marquee that covers the stage and names the "
            "site manager as its owner; for a cancellation it agrees a standby local act and "
            "names the bookings volunteer; for the late toilets it decides to accept the risk "
            "and says so in the register. Each response carries one name and a date by which "
            "it has to be in place."
        ),
        pitfalls=(
            'Writing "monitor the weather" as a response, which is a plan to keep worrying '
            "rather than a plan to act.",
            "Assigning a response to the committee as a whole, so nobody actually makes the "
            "booking.",
            "Planning only against threats and ignoring a bigger crowd than expected, which "
            "also needs a decision.",
        ),
    ),
    "11.6": ProcessContent(
        plain_summary="Carry out the risk responses that were planned, not just leave them on paper.",
        why_bother=(
            "A response plan that sits unused when the risk actually occurs protects "
            "nobody; this is where the planning finally pays off."
        ),
        done_when="Planned responses are being carried out and their effect on the risk is tracked.",
        first_time_tip=(
            "Check in with each response owner before the risk actually triggers, not "
            "after. Confirming readiness early avoids a scramble in the moment."
        ),
        worked_example=(
            "Two weeks out, the site manager confirms the marquee is booked and paid for, and "
            "the bookings volunteer has the standby act's written agreement in hand. The "
            "chair checks both off at the meeting instead of assuming they happened, and the "
            "register records the date each response actually went into place."
        ),
        pitfalls=(
            "Assuming a response that was planned is a response that happened.",
            "Carrying out the response but never recording it, so the register still shows "
            "the risk untreated.",
            "Leaving the booking until the risk looks likely, by which time the marquee is "
            "already hired out.",
        ),
    ),
    "11.7": ProcessContent(
        plain_summary="Keep watching for new risks and check whether existing responses still work.",
        why_bother=(
            "A risk register frozen at kickoff goes stale fast; new threats appear and old "
            "ones change shape as the project moves forward."
        ),
        done_when="The risk register is being actively reviewed and updated as the project proceeds.",
        first_time_tip=(
            "Put a risk review on the same recurring calendar slot as your status meeting. "
            "A review that only happens when someone remembers rarely happens at all."
        ),
        worked_example=(
            "At each weekly meeting in the month before the festival the committee walks the "
            "register. The forecast has turned settled, so the storm drops down the list, but "
            "a new risk has appeared: the roadwork on the approach now overlaps the festival "
            "weekend and could block the delivery route. It is logged, rated and given an "
            "owner the same way as the rest."
        ),
        pitfalls=(
            "Reviewing the register only when somebody remembers, which in a busy month means "
            "not at all.",
            "Adding new risks but never closing or lowering the ones that have passed.",
            "Checking that responses still exist without checking they still work after the "
            "plan has changed.",
        ),
    ),
}
