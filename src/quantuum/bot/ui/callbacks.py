from aiogram.filters.callback_data import CallbackData


class ProfileCb(CallbackData, prefix="prof"):
    action: str  # edit
    field: str = ""


class HistoryCb(CallbackData, prefix="hist"):
    action: str  # page | open
    page: int = 0
    bp_id: int = 0


class BlueprintCb(CallbackData, prefix="bp"):
    action: str  # download | preview | back
    bp_id: int


class OnboardCb(CallbackData, prefix="onb"):
    action: str  # start | cancel


class OwnerOnboardCb(CallbackData, prefix="own"):
    action: str  # confirm | cancel
