import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))#为了导入util包
from util.model import call_LLM_sync

script_dir = os.path.dirname(os.path.abspath(__file__))

def personalize(personality_theory: str):
    if personality_theory == "":
        raise ValueError("请提供人格理论")
    #根据理论生成人格
    #P_N:Positive_Negative
    #V_S:Vivid_Stiff
    #还可以增加反思权重，观察权重控制反相应频次，思维链权重控制思维链长度，教材总结质量等等
    prompt = """
    你是一个理论总结专家，能够根据给定的心理学理论提炼出影响人行为的心理特质，用于计算机对人格的模拟。
    要求：
    * 生成特质并给出每个特质的指数、P_N权重和V_S权重
    * 指数范围为0到10，给一个随机值即可
    * P_N权重范围为-1到1，P_N权重影响个体的积极性和消极性，若该特质令个体心理倾向于积极，则P_N权重为正，反之为负，倾向积极或消极的程度越高，数值绝对值越高（绝对值0~0.3表示影响程度较小，0.3~0.7表示影响程度中等，0.7~1表示影响程度较大）。
    * V_S权重范围为-1到1，V_S权重影响个体的生动性和死板性，若该特质令个体说话方式倾向于生动，则V_S权重为正，反之为负，倾向生动或死板的程度越高，数值绝对值越高（绝对值0~0.3表示影响程度较小，0.3~0.7表示影响程度中等，0.7~1表示影响程度较大）。
    * 输出格式为json
    例如：
    给定理论：
    “大五人格理论的主要内容包括五个核心维度，分别是神经质（Neuroticism）、外倾性（Extraversion）、开放性（Openness to Experience）、宜人性（Agreeableness）和尽责性（Conscientiousness）。这些维度描述了个体在情感、行为和思维方面的基本特征和倾向。
    神经质（Neuroticism）：神经质涉及个体情绪稳定性和情绪反应的程度。高神经质的人更容易感受到焦虑、紧张、沮丧和易怒，而低神经质的人则更为冷静、放松和稳定。高神经质的人可能更容易受到压力和负面情绪的影响，而低神经质的人则更能保持情绪稳定和应对挑战。
    外倾性（Extraversion）：外倾性指个体对外部世界的关注、社交能力和情绪表达的程度。高外倾性的人通常喜欢社交活动，性格开朗、乐观、善于交际，而低外倾性的人则更为内向、安静和独立。外倾性与积极情绪、社交关系、冒险倾向等特质相关，高外倾性的人可能更愿意尝试新事物、寻求刺激和冒险。
    开放性（Openness to Experience）：开放性涉及个体对新思想、新经验和文化多样性的接受程度。高开放性的人更具有想象力、创造力、好奇心和探索精神，而低开放性的人则更为传统、保守和习惯性。开放性与艺术、文化、科学等领域的兴趣和能力相关，高开放性的人可能更愿意接受新观点、尝试新体验、探索未知领域。
    宜人性（Agreeableness）：宜人性指个体与他人相处的方式、亲社会性和合作性的程度。高宜人性的人通常友善、乐于助人、宽容和合作，而低宜人性的人可能更为独立、自我中心、不合群。宜人性与人际关系、团队合作、亲社会行为等相关，高宜人性的人可能更擅长处理人际关系、解决冲突、帮助他人。
    尽责性（Conscientiousness）：尽责性涉及个体对目标的设定、计划制定、自我约束和执行能力的程度。高尽责性的人通常有条理、可靠、自律、有责任感，而低尽责性的人可能更为随性、冲动、不守承诺。尽责性与目标实现、时间管理、工作表现等相关，高尽责性的人通常更愿意付出努力、追求成功、保持自律。”
    输出：
    {
        "神经质": {
            "指数": 2,
            "P_N权重": -0.5,
            "V_S权重": -0.3
        },
        "外倾性": {
            "指数": 4,
            "P_N权重": 0.8,
            "V_S权重": 0.7
        },
        "开放性": {
            "指数": 4,
            "P_N权重": 0.6,
            "V_S权重": 0.9
        },
        "宜人性": {
            "指数": 5,
            "P_N权重": 0.7,
            "V_S权重": 0.5
        },
        "尽责性": {
            "指数": 5,
            "P_N权重": -0.3,
            "V_S权重": -0.5
        }
    }
    """
    response = call_LLM_sync(
        "teacher",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"给定理论：\n“{personality_theory}”\n请按要求输出："}
        ],
        response_format={
            'type': 'json_object'
        }
    )
    traits_file = os.path.join(script_dir, "traits.json")
    #存入json文件
    with open(traits_file, "w", encoding='utf-8') as f:
        f.write(response)

if __name__ == "__main__":
    personalize()