#pragma once
#include "service_7.h"
#include "model_7.h"
#include <memory>

class Controller7 {
public:
    Controller7();
    void initialize();
    void run();
private:
    std::unique_ptr<Service7> service_;
    std::shared_ptr<Model7> model_;
};
