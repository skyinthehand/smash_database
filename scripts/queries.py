from datetime import datetime

# event.sets / phaseGroup.sets のどちらからでも同じノード形状で取得できるよう、
# フィールド選択を共有定数として切り出したもの(通常版)。
_SET_NODE_FIELDS = """id
            state
            winnerId
            round
            fullRoundText
            phaseGroup {
              id
              displayIdentifier
              phase {
                phaseOrder
              }
              wave {
                id
                identifier
              }
            }
            slots {
              id
              entrant {
                id
                participants {
                  user {
                    id
                  }
                }
              }
              standing {
                stats {
                  score {
                    label
                    value
                  }
                }
              }
            }
            games {
              id
              orderNum
              winnerId
              entrant1Score
              entrant2Score
              stage {
                id
                name
              }
              selections {
                id
                entrant {
                  id
                  participants {
                    user {
                      id
                    }
                  }
                }
                character {
                  id
                  name
                }
              }
            }"""

# 軽量版(matches_only 用): slots.entrant.participants と games.selections を省いたもの。
_SET_NODE_FIELDS_LIGHT = """id
            state
            winnerId
            round
            fullRoundText
            phaseGroup {
              id
              displayIdentifier
              phase {
                phaseOrder
              }
              wave {
                id
                identifier
              }
            }
            slots {
              id
              entrant {
                id
              }
              standing {
                stats {
                  score {
                    label
                    value
                  }
                }
              }
            }
            games {
              id
              orderNum
              winnerId
              entrant1Score
              entrant2Score
              stage {
                id
                name
              }
            }"""

def get_event_sets_query():
    return f"""query EventSets($eventId: ID!, $page: Int!, $perPage: Int!) {{
      event(id: $eventId) {{
        id
        name
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {{
          pageInfo {{
            total
            totalPages
          }}
          nodes {{
            {_SET_NODE_FIELDS}
          }}
        }}
      }}
    }}"""

def get_event_sets_light_query():
    return f"""query EventSetsLight($eventId: ID!, $page: Int!, $perPage: Int!) {{
      event(id: $eventId) {{
        id
        name
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {{
          pageInfo {{
            total
            totalPages
          }}
          nodes {{
            {_SET_NODE_FIELDS_LIGHT}
          }}
        }}
      }}
    }}"""

def get_phase_group_sets_query():
    return f"""query PhaseGroupSets($phaseGroupId: ID!, $page: Int!, $perPage: Int!) {{
      phaseGroup(id: $phaseGroupId) {{
        id
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {{
          pageInfo {{
            total
            totalPages
          }}
          nodes {{
            {_SET_NODE_FIELDS}
          }}
        }}
      }}
    }}"""

def get_phase_group_sets_light_query():
    return f"""query PhaseGroupSetsLight($phaseGroupId: ID!, $page: Int!, $perPage: Int!) {{
      phaseGroup(id: $phaseGroupId) {{
        id
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {{
          pageInfo {{
            total
            totalPages
          }}
          nodes {{
            {_SET_NODE_FIELDS_LIGHT}
          }}
        }}
      }}
    }}"""

def get_standings_query():
    return """query EventStandings($eventId: ID!, $page: Int!, $perPage: Int!) {
      event(id: $eventId) {
        standings(query: {page: $page, perPage: $perPage}) {
          pageInfo {
            totalPages
          }
          nodes {
            placement
            entrant {
              id
              name
              participants {
                user {
                  id
                  genderPronoun
                  discriminator
                  authorizations(types: [TWITTER, DISCORD]) {
                    externalId
                    externalUsername
                    type
                  }
                }
                player {
                  id
                  gamerTag
                  prefix
                }
              }
            }
          }
        }
      }
    }"""

def get_seeds_query():
    return """query PhaseSeeds($phaseId: ID!, $page: Int!, $perPage: Int!) {
      phase(id: $phaseId) {
        id
        seeds(query: {
          page: $page
          perPage: $perPage
        }) {
          pageInfo {
            total
            totalPages
          }
          nodes {
            id
            seedNum
            entrant {
              id
              participants {
                user {
                  id
                  genderPronoun
                  discriminator
                  authorizations(types: [TWITTER, DISCORD]) {
                    externalId
                    externalUsername
                    type
                  }
                }
                player {
                  id
                  gamerTag
                  prefix
                }
              }
            }
          }
        }
      }
    }"""

def get_user_query():
    return """query UserDetails($userId: ID!) {
      user(id: $userId) {
        id
        genderPronoun
        discriminator
        authorizations(types: [TWITTER, DISCORD]) {
          externalId
          externalUsername
          type
        }
      }
    }"""

def get_user_player_query():
    return """query UserAndPlayer($userId: ID!, $playerId: ID!) {
      user(id: $userId) {
        id
        genderPronoun
        discriminator
        authorizations(types: [TWITTER, DISCORD]) {
          externalId
          externalUsername
          type
        }
      }
      player(id: $playerId) {
        id
        gamerTag
        prefix
      }
    }"""

def get_tournament_events_query():
    return """query TournamentEvents($tournamentId: ID!, $gameId: ID!) {
      tournament(id: $tournamentId) {
        id
        name
        events(filter: {videogameId: [$gameId]}) {
          id
          name
          startAt
          isOnline
          state
          type
        }
      }
    }""" 

def get_event_entrants_query():
    return """query EventEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
      event(id: $eventId) {
        entrants(query: {page: $page, perPage: $perPage}) {
          pageInfo {
            totalPages
          }
          nodes {
            id
            participants {
              user {
                id
              }
            }
          }
        }
      }
    }"""

def get_phase_groups_query():
    return """query PhaseGroupsByEvent($eventId: ID!, $page: Int!, $perPage: Int!) {
      event(id: $eventId) {
        phases {
          id
          phaseGroups(query: {page: $page, perPage: $perPage}) {
            pageInfo {
              total
            }
            nodes {
              id
              displayIdentifier
            }
          }
        }
      }
    }"""

def get_tournaments_by_game_query(country_code="", before_now=True, past=False):
    first_row = """query TournamentsByGame($gameId: ID!, $perPage: Int!, $page: Int!) {"""
    second_row = """tournaments(query: {perPage: $perPage, page: $page, sortBy: "startAt desc", filter: {videogameIds: [$gameId], published: true, *other_filters*}}) {"""
    nodes_query = """nodes {
            id
            name
            startAt
            endAt
            countryCode
            isOnline
            addrState
            city
            countryCode
            lat
            lng
            mapsPlaceId
            postalCode
            venueAddress
            venueName
            timezone
            url
          }
          pageInfo {
            totalPages
          }
        }
      }"""
    
    filters = ""
    if country_code:
      filters += f' ,countryCode: "{country_code}" '
    if past:
      filters += """ ,past: true """
    if before_now:
      filters += f" ,beforeDate: {int(datetime.now().timestamp())} "
    
    second_row = second_row.replace("*other_filters*", filters)

    query = "\n".join([first_row, second_row, nodes_query])
    return query

def get_tournament_url_query():
    return """query Tournament($tournamentId: ID!) {
      tournament(id: $tournamentId) {
        url
      }
    }"""

def get_event_details_by_tournament_query():
    """トーナメントスラッグからイベント詳細を取得するGraphQLクエリ"""
    return """
    query TournamentEventsQuery($tournamentSlug: String!, $eventSlug: String!) {
      tournament(slug: $tournamentSlug) {
        id
        name
        slug
        countryCode
        city
        lat
        lng
        venueName
        timezone
        postalCode
        venueAddress
        mapsPlaceId
        url
        endAt
        events(filter: {slug: $eventSlug}) {
          id
          name
          slug
          startAt
          isOnline
          numEntrants
          state
          type
        }
      }
    }
    """

def get_tournament_by_id_query():
    return """query TournamentById($tournamentId: ID!) {
      tournament(id: $tournamentId) {
        id
        name
        startAt
        endAt
        countryCode
        city
        lat
        lng
        mapsPlaceId
        postalCode
        venueAddress
        venueName
        timezone
        url
      }
    }"""

def get_event_details_by_id_query():
    return """query EventById($eventId: ID!) {
      event(id: $eventId) {
        id
        name
        slug
        startAt
        numEntrants
        isOnline
        state
        type
        tournament {
          id
          name
          slug
          startAt
          endAt
          countryCode
          city
          lat
          lng
          venueName
          timezone
          postalCode
          venueAddress
          mapsPlaceId
          url
        }
      }
    }"""
