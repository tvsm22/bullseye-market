"""Офлайн-проверка сопоставления на выдуманной выдаче 5ka (структура как у catalog/v3/search)."""

import unittest

from r2c.matcher import match, parse_pack
from r2c.racion import Need


def need(key, name, unit, needed):
    return Need(key=key, name=name, group="", unit=unit, needed=needed, buy=0, packs=0, pack=0,
                loose=False, racion_cost=0)


def prod(plu, name, clar, price, uom="шт", discount=None, avail=True, step="1.0"):
    return {"plu": plu, "name": name, "property_clarification": clar, "uom": uom, "step": step,
            "prices": {"regular": str(price), "discount": discount and str(discount), "cpd_promo_price": None},
            "is_available": avail}


class PackTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_pack("930 мл"), (930, "ml"))
        self.assertEqual(parse_pack("1,5 кг"), (1500, "g"))
        self.assertEqual(parse_pack("Йогурт 6х100г"), (600, "g"))
        self.assertEqual(parse_pack("Яйца С1 10шт"), (10, "pcs"))
        self.assertEqual(parse_pack("1 л"), (1000, "ml"))
        self.assertIsNone(parse_pack("Огурцы гладкие"))


class MatchTest(unittest.TestCase):
    def test_milk_pack_and_fat(self):
        products = [
            prod(1, "Шоколад молочный 90г", "90 г", 79),
            prod(2, "Молоко Простоквашино 3,2% 930мл", "930 мл", 109),
            prod(3, "Молоко Домик в деревне 2,5% 1,4л", "1,4 л", 149),
            prod(4, "Молоко Красная цена 2,5% 900мл", "900 мл", 75),
        ]
        m = match(need("milk", "Молоко 2,5%", "ml", 635.5), products, {})
        self.assertEqual(m.best.plu, "4")  # 2,5 %, одна упаковка ≥ 635 мл, дешевле
        self.assertEqual(m.best.qty, 1)
        self.assertNotEqual(m.confidence, "low")

    def test_eggs_count(self):
        products = [prod(10, "Яйца куриные С1 10шт", "10 шт", 120), prod(11, "Яйца куриные С0 20шт", "20 шт", 260)]
        m = match(need("eggs", "Яйца куриные", "pcs", 79.1), products, {})
        self.assertEqual(m.best.plu, "10")
        self.assertEqual(m.best.qty, 8)

    def test_loose_by_weight(self):
        products = [prod(20, "Огурцы среднеплодные", "", 199.99, uom="кг", step="0.1")]
        m = match(need("cucumber", "Огурцы", "g", 2870), products, {})
        self.assertTrue(m.best.loose)
        self.assertAlmostEqual(m.best.qty, 2.8)  # с допуском 3 %
        self.assertAlmostEqual(m.best.cost, 2.8 * 199.99)

    def test_head_word(self):
        products = [prod(30, "Чипсы со вкусом сыра 150г", "150 г", 120), prod(31, "Сыр Российский 200г", "200 г", 210)]
        m = match(need("cheese_hard", "Сыр твёрдый", "g", 533), products, {"ingredients": {"cheese_hard": {"query": "сыр"}}})
        self.assertEqual(m.best.plu, "31")
        self.assertEqual(m.best.qty, 3)

    def test_pin_and_avoid(self):
        products = [prod(40, "Фарш Домашний свино-говяжий 500г", "500 г", 300), prod(41, "Фарш свино-говяжий 400г", "400 г", 250)]
        cfg = {"ingredients": {"ground_mixed": {"plu": "41"}}}
        m = match(need("ground_mixed", "Фарш свино-говяжий", "g", 553.5), products, cfg)
        self.assertEqual((m.best.plu, m.best.qty, m.confidence), ("41", 2, "high"))
        m = match(need("ground_mixed", "Фарш", "g", 300), products, {"avoid_words": ["домашний"]})
        self.assertEqual(m.best.plu, "41")

    def test_unavailable_and_nothing(self):
        m = match(need("dill", "Укроп", "g", 50), [prod(50, "Укроп 50г", "50 г", 60, avail=False)], {})
        self.assertEqual(m.confidence, "none")


if __name__ == "__main__":
    unittest.main()
