class NavigationAssistedDecisions:
  def __init__(self):
    self.active = False
    self.approaching_intersection = False
    self.approaching_turn = False
    self.route_context_available = False
    self.reason = "disabled"

  def reset(self):
    self.active = False
    self.approaching_intersection = False
    self.approaching_turn = False
    self.route_context_available = False
    self.reason = "disabled"

  def update(self, sm):
    # Placeholder only: future control changes should stay behind this feature flag.
    if "frogpilotNavigation" not in sm.data:
      self.reset()
      self.reason = "route_context_unavailable"
      return

    frogpilot_navigation = sm["frogpilotNavigation"]

    self.route_context_available = True
    self.approaching_intersection = frogpilot_navigation.approachingIntersection
    self.approaching_turn = frogpilot_navigation.approachingTurn
    self.active = self.approaching_intersection or self.approaching_turn

    if self.approaching_intersection:
      self.reason = "intersection"
    elif self.approaching_turn:
      self.reason = "turn"
    else:
      self.reason = "route_monitoring"
