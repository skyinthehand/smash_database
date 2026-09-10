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

def get_event_set_ids_query():
    """setの詳細(slots/games/selections等)を一切要求せず、idのみを取得する軽量クエリ。
    一括取得(event.sets)が失敗したイベントで、逐次取得モードのプレースホルダー投入に
    使う set_id 一覧を、低いcomplexityコストで取得するためのもの。"""
    return """query EventSetIds($eventId: ID!, $page: Int!, $perPage: Int!) {
      event(id: $eventId) {
        id
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {
          pageInfo {
            total
            totalPages
          }
          nodes {
            id
          }
        }
      }
    }"""

def get_phase_group_set_ids_query():
    """get_event_set_ids_query() の phaseGroup 単位版。excluded_phases.json により
    既知の問題phaseGroupを除外する必要があるイベントで使う。"""
    return """query PhaseGroupSetIds($phaseGroupId: ID!, $page: Int!, $perPage: Int!) {
      phaseGroup(id: $phaseGroupId) {
        id
        sets(
          page: $page
          perPage: $perPage
          sortType: STANDARD
        ) {
          pageInfo {
            total
            totalPages
          }
          nodes {
            id
          }
        }
      }
    }"""

def get_sets_by_ids_query(set_ids):
    """複数のset_idを、ルートの set(id: ID!) フィールドをGraphQLエイリアスで
    バッチ化して直接取得するクエリを組み立てる。1リクエストのcomplexityは
    set_idsの件数×_SET_NODE_FIELDSの固定コストで決まり、イベントの総set数には
    依存しない。"""
    variable_defs = ", ".join(f"$id{i}: ID!" for i in range(len(set_ids)))
    fields = "\n".join(
        f"""s{i}: set(id: $id{i}) {{
            {_SET_NODE_FIELDS}
          }}"""
        for i in range(len(set_ids))
    )
    return f"""query SetsByIds({variable_defs}) {{
      {fields}
    }}"""

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

def get_player_user_query():
    """participant.user が null だった参加者について、player(id:) を個別に引き直し、
    player.user.id 経由で同じ start.gg アカウントへのリンクが解決できるかを確認する
    ための軽量クエリ。標準の standings/seeds ページ取得クエリには含めない(全参加者分の
    コストが底上げされ、complexity上限に当たりやすくなるため)。"""
    return """query PlayerUser($playerId: ID!) {
      player(id: $playerId) {
        id
        user {
          id
        }
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
              player {
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

def get_upcoming_tournaments_by_game_query(country_code, after_date):
    """未開催トーナメント一覧クエリ。既存の get_tournaments_by_game_query() とは
    独立した別関数とし、既存呼び出し元(履歴クロール側)には一切影響を与えない。
    afterDate で開始日時が未来の大会のみに絞り込み、nodes に events をネストする
    ことで、参加人数(numEntrants)を大会一覧の取得と同時に(1リクエストで)
    取得できるようにする(010-upcoming-tournaments、research.md #1/#2)。"""
    first_row = """query UpcomingTournamentsByGame($gameId: ID!, $perPage: Int!, $page: Int!) {"""
    second_row = f"""tournaments(query: {{perPage: $perPage, page: $page, sortBy: "startAt desc", filter: {{videogameIds: [$gameId], published: true, countryCode: "{country_code}", afterDate: {after_date}}}}}) {{"""
    nodes_query = """nodes {
            id
            name
            startAt
            endAt
            countryCode
            isOnline
            addrState
            city
            lat
            lng
            mapsPlaceId
            postalCode
            venueAddress
            venueName
            timezone
            url
            events(filter: {videogameId: [$gameId]}) {
              id
              name
              numEntrants
              state
              type
              isOnline
              startAt
            }
          }
          pageInfo {
            totalPages
          }
        }
      }"""

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
