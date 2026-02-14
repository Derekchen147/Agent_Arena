"""SessionManager 单元测试。"""

import os
import pytest
from src.core.session_manager import SessionManager


@pytest.fixture
async def session_manager(tmp_path):
    db_path = str(tmp_path / "test.db")
    sm = SessionManager(db_path=db_path)
    await sm.initialize()
    yield sm
    await sm.close()


async def test_create_and_get_group(session_manager):
    group = await session_manager.create_group("测试群组", "这是测试")
    assert group.name == "测试群组"
    assert group.id

    fetched = await session_manager.get_group(group.id)
    assert fetched is not None
    assert fetched.name == "测试群组"


async def test_list_groups(session_manager):
    await session_manager.create_group("群组A")
    await session_manager.create_group("群组B")
    groups = await session_manager.list_groups()
    assert len(groups) == 2


async def test_add_and_list_members(session_manager):
    group = await session_manager.create_group("测试群组")
    member = await session_manager.add_member(
        group.id, member_type="agent", agent_id="architect", display_name="架构师"
    )
    assert member.agent_id == "architect"

    members = await session_manager.list_group_members(group.id)
    assert len(members) == 1


async def test_save_and_get_messages(session_manager):
    group = await session_manager.create_group("测试群组")
    await session_manager.save_message(
        group_id=group.id,
        author_id="human",
        content="你好",
        author_type="human",
        author_name="用户",
    )
    await session_manager.save_message(
        group_id=group.id,
        author_id="architect",
        content="你好，有什么需要帮忙的？",
        author_type="agent",
        author_name="架构师",
    )

    messages = await session_manager.get_messages(group.id)
    assert len(messages) == 2
    assert messages[0].content == "你好"
    assert messages[1].author_type == "agent"


async def test_delete_group(session_manager):
    group = await session_manager.create_group("要删除的群组")
    await session_manager.delete_group(group.id)
    fetched = await session_manager.get_group(group.id)
    assert fetched is None
