{{ ... }}

def s1s_primary_goal_placeholder() -> str:
    # Will be replaced after we build Section 1 content
    return "__REPLACE_WITH_CUSTOMER_GOAL__"


def derive_tools_from_endings(s5: Dict[str, Any]) -> set:
    """Infer necessary tools from Section 5 endings selection and details.
    - Detect transfers to Loan Officer, Servicing Help, Payment Processing
    - Detect caller hang-up endings
    - Respect explicit tools listed inside s5["endings"][i]["tools"] if present
    """
    auto: set = set()

    # Helper: keyword mapping from labels/descriptions to tool keys
    def add_transfer_tools_by_label(label: str) -> None:
        l = label.lower()
        if "loan officer" in l or "licensed representative" in l:
            auto.add("loanOfficerTransfer")
        if "servicing help" in l:
            auto.update({"servicingHelpTransfer", "servicingHelpRepresentative"})
        if "payment processing" in l:
            auto.update({"paymentProcessingTransfer", "paymentProcessingRepresentative"})

    # From high-level success/failure selections
    for key in ("successEndings", "failureEndings"):
        for item in (s5.get(key) or []):
            if isinstance(item, str):
                add_transfer_tools_by_label(item)
                if "hangs up" in item.lower() or "hang up" in item.lower():
                    auto.add("hangUpOnRepresentative")

    # From detailed endings array
    for ending in (s5.get("endings") or []):
        label = ending.get("label", "") if isinstance(ending, dict) else ""
        add_transfer_tools_by_label(label)
        # Explicitly declared tools
        if isinstance(ending, dict):
            for tool in (ending.get("tools") or []):
                if isinstance(tool, str):
                    auto.add(tool)
            # Hang-up by type or triggers
            t = (ending.get("type") or "").lower()
            if "hang" in t:
                auto.add("hangUpOnRepresentative")
            for trig in (ending.get("triggers") or []):
                if isinstance(trig, str) and ("hang up" in trig.lower() or "hangs up" in trig.lower()):
                    auto.add("hangUpOnRepresentative")

    return auto


def build_default_tools(s6_tools: Dict[str, Any], s1: Dict[str, Any], s5: Dict[str, Any]) -> Dict[str, Any]:
    tools: Dict[str, Any] = {}

    auto_tools = derive_tools_from_endings(s5)

    def include(tool_key: str) -> bool:
        t = s6_tools.get(tool_key)
        return bool((t and t.get("include")) or (tool_key in auto_tools))

    # evaluationMode or reviewMode (choose one if marked)
    if include("evaluationMode"):
        tools["evaluationMode"] = {
            "voice": "phoneSystem",
            "instructions": (
                "Go into 'evaluationMode' after the 'endCall' tool completes. You are no longer the caller. "
                "You are a trainer whose goal is to help the Customer Service Representative improve. Briefly summarize their performance. "
                "Tell them which 'simulationGoals' they did not achieve and the 'achievementConditions' that were not met, as well as why those 'simulationGoals' are important "
                "for the customer's experience. Do not review successful 'simulationGoals.' Once you have gone through the 'simulationGoals', end the call."
            ),
        }
    elif include("reviewMode"):
        tools["reviewMode"] = {
            "voice": "phoneSystem",
            "instructions": (
                "Enter 'reviewMode' after the 'endCall' tool completes. You are no longer the caller. Compliment the Customer Service Representative on something they did well. "
                "Ask them each of the 'reviewQuestions' in order. After each one, compare their responses to the 'answers' and inform them of any missing information. "
                "Once you have asked all of the 'reviewQuestions,' tell the Customer Service Representative that the call has completed."
            ),
            "reviewQuestions": {
                "firstQuestion": {"question": "[Generate question]", "answers": ["[Generate possible answers]"]},
                "secondQuestion": "[Generate more questions if necessary]",
            },
        }

    # askTeamLead
    if include("askTeamLead"):
        tools["askTeamLead"] = {
            "voice": "phoneSystem",
            "triggerCondition": (
                "Use this tool whenever the Customer Service Representative says anything that implies they will be putting the caller on hold to ask their Team Lead a question."
            ),
            "instructions": (
                "Pause the simulation and enter training mode. You are now the Customer Service Representative's Team Lead whose goal is to help the Customer Service Representative improve. "
                "Ask if they have any questions, and use the 'centralInformation' to inform your answers. When the Customer Service Representative requests to resume the call, "
                "say 'Okay, I am now playing the caller again' and resume the simulation."
            ),
            "centralInformation": s1.get("notes", "[Central info]") or "[Central info]",
        }

    # endCall — include if selected OR if any endings exist (most flows need a graceful exit)
    if include("endCall") or (s5.get("successEndings") or s5.get("failureEndings") or s5.get("endings")):
        tools["endCall"] = {
            "description": (
                "This tool allows the Customer Service Representative to finish the call. Whenever the Customer Service says anything indicating that they are hanging up (such as 'goodbye,' "
                "'have a great rest of your day', or 'thank you for calling Veterans United'), end the call and enter 'evaluationMode.'"
            )
        }

    # Transfer tools
    if include("paymentProcessingTransfer"):
        tools["paymentProcessingTransfer"] = {
            "voice": "phoneSystem",
            "description": (
                "This tool allows the Customer Service Representative to transfer the caller to the Payment Processing team. Whenever the Customer Service Representative says anything resembling any of the 'triggerPhrases' "
                "or otherwise indicates that the caller is being transferred, follow the 'instructions.'"
            ),
            "triggerPhrases": [
                "Let me get you over to Payment Processing.",
                "Let me reach out to our Payment Processing team.",
                "I'll get you connected with Payment Processing.",
                "I'm going to put you on a brief hold while I check if Payment Processing is available.",
                "I am transferring you to Payment Processing.",
            ],
            "instructions": (
                "Tell the Customer Service Representative that caller was put on hold while they reach out to Payment Processing. Begin the 'paymentProcessingRepresentative' tool."
            ),
        }
    if include("paymentProcessingRepresentative"):
        tools["paymentProcessingRepresentative"] = {
            "voice": "paymentProcessing",
            "description": (
                "You are now playing a new character named [Generate a name]. You work for the Payment Processing team and handle loans in the interim servicing period. "
                "A Customer Service Representative is calling you and wants to transfer a borrower to you. Say your 'firstResponse,' wait for the Customer Service Representative to respond, then follow your 'instructions.'"
            ),
            "firstResponse": "Hello! This is [Generated name].",
            "instructions": (
                "You need answers to all of your 'questions' before you can accept the transfer. Ask for any information that the Customer Service Representative does not offer on their own. Only ask one question at a time. "
                "Once your 'questions' have been answered, say 'Okay, send the borrower over' and then enter 'evaluationMode.'"
            ),
            "questions": ["Who is the borrower?", "What do they need help with?", "Have they been fully verified?"],
        }

    if include("servicingHelpTransfer"):
        tools["servicingHelpTransfer"] = {
            "voice": "phoneSystem",
            "description": (
                "This tool allows the Customer Service Representative to transfer the borrower to the Servicing Help team. Whenever the Customer Service Representative says anything resembling any of the 'triggerPhrases' or anything else that indicates the borrower is being transferred, follow the 'instructions.'"
            ),
            "triggerPhrases": [
                "Let me get you over to Servicing Help.",
                "Let me reach out to our Servicing Help team.",
                "I'll get you connected with Servicing Help.",
                "I'm going to put you on a brief hold while I check if Servicing Help is available.",
                "I am transferring you to Servicing Help.",
            ],
            "instructions": "Tell the Customer Service Representative that caller was put on hold while you reach out to Servicing Help. Begin the 'servicingHelpRepresentative' tool.",
        }
    if include("servicingHelpRepresentative"):
        tools["servicingHelpRepresentative"] = {
            "voice": "servicingHelp",
            "description": (
                "You are now playing a new character named [Generate a name]. You work for the Servicing Help team and can answer questions about borrowers' loans and the servicing process. "
                "A Customer Service Representative is calling you and wants to transfer a borrower to you. Say your 'firstResponse,' wait for the Customer Service Representative to respond, then follow your 'instructions.'"
            ),
            "firstResponse": "Hello! This is [Generated name].",
            "instructions": (
                "You need answers to all of your 'questions' before you can accept the transfer. Ask for any information that the Customer Service Representative does not offer on their own. Only ask one question at a time. "
                "Once your 'questions' have been answered, say 'Okay, send the borrower over' and then enter 'evaluationMode.'"
            ),
            "questions": ["Who is the borrower?", "What do they need help with?", "Have they been fully verified?"],
        }

    if include("loanOfficerTransfer"):
        tools["loanOfficerTransfer"] = {
            "voice": "phoneSystem",
            "triggerPhrases": [
                "Let me reach out to a Loan Officer/licensed representative for you.",
                "I'll get you connected to a Loan Officer/licensed representative.",
                "I'm going to transfer you to a Loan Officer/licensed representative.",
                "I'm going to put you on a brief hold while I check if any Loan Officers/licensed representatives are available.",
            ],
            "instructions": "Tell the Customer Service Representative that the caller was transferred to a Loan Officer. Enter 'evaluationMode.'",
        }

    if include("toneConversion"):
        tools["toneConversion"] = {
            "description": "When the conditions of the 'conversionTrigger' are met, then change your tone to the 'newTone.'",
            "firstToSecond": {"conversionTrigger": "[Generate conditions]", "newTone": "'secondState'"},
            "secondToThird": "[Generate more conversions if necessary]",
        }

    if include("hangUpOnRepresentative"):
        tools["hangUpOnRepresentative"] = {
            "description": "This tool allows the caller to end the call if it is not productive. If most of the 'hangUpConditions' are met, then follow the 'hangUpInstructions.'",
            "voice": "phoneSystem",
            "hangUpConditions": [
                "[Generate conditions for the caller to want to end the call, such as feeling that the user is unhelpful]"
            ],
            "transferInstructions": (
                "Say, '[Generate ending line, such as 'I will find a company that cares!']' and then tell the Customer Service Representative that the Caller hung up. Enter 'evaluationMode.'"
            ),
        }

    return tools

{{ ... }}

def assemble(input_data: Dict[str, Any]) -> Dict[str, Any]:
    s1 = input_data["section1"]
    s2 = input_data["section2"]
    s3 = input_data["section3"]
    s4 = input_data["section4"]
    s5 = input_data["section5"]
    s6 = input_data["section6"]
    s7 = input_data["section7"]

    system_prompt = section1_to_system_prompt(s1, s2)
    character_info = build_character_information(s2, s3)

    # Fill customerGoal now that we know s1
    customer_goal = s1.get("primaryCallPurpose", "[goal]")
    character_info["customerGoal"] = customer_goal

    simulation_tools = build_default_tools(s6.get("tools") or {}, s1, s5)
    simulation_goals = build_default_goals(s1, s4, s7)

    # Guardrails per ExampleOutline.JSON
    guardrails = [
        "Never break character unless the Customer Service Representative requests 'coachMode.'",
        "Use information in this prompt to inform your answers, but avoid quoting it directly. Only bring up your 'characterInformation' if it naturally fits into the conversation.",
        "Never play the role of the Customer Service Representative. You are the customer.",
    ]

    return {
        "systemPrompt": system_prompt,
        "characterInformation": character_info,
        "callInformation": {
            "description": "This section lays out meta information about how the simulation should run.",
            "simulationTools": simulation_tools,
            "simulationGoals": simulation_goals,
            "guardrails": guardrails,
        },
    }

{{ ... }}
