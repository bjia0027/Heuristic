#pragma once
#include <functional>
#include <vector>

class Service12 {
public:
    Service12();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
